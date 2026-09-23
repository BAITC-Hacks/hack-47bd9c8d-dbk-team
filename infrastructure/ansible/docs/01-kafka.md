# Runbook: Kafka (KRaft single-broker)

## Профиль сервиса

| Параметр | Значение |
|---|---|
| Каталог стека | `/opt/kafka` (на хосте группы `kafka` / `app`) |
| Контейнер | `kafka` (broker+controller, KRaft без ZooKeeper) |
| Юниты systemd | `kafka.service` (up -d / down), `kafka-deploy.service` (pull + up -d) |
| Данные | `/opt/kafka/data` |
| Образ | `apache/kafka:3.9.0` — запинен в compose-шаблоне |
| Внутренний порт | 9092 (PLAINTEXT, advertised = адрес хоста) |
| Внешний порт | 9093 (EXTERNAL, SASL_SSL/PLAIN, юзер `admin`, пароль в vault) |
| Веб-морда | Kafbat UI, порт 8181 (login `admin`, пароль = `SPRING_SECURITY_USER_PASSWORD` из vault), юнит `kafka-ui.service` |
| Топики | `AiMeetingCopilotRequest`, `AiMeetingCopilotResponse` |
| Группы | `ai-meeting-copilot` (воркер приложения) |
| Зависимости | docker.service; от kafka зависит воркер meeting-copilot |

Критичность: высокая. Kafka лежит → воркер не получает задач, все
запросы висят без обработки (запросившая сторона ждёт ответ в
`AiMeetingCopilotResponse`).

## Особенность: userns-remap

Если на хосте включён userns-remap, каталог `/opt/kafka/data` должен
принадлежать `101000:101000` (uid 1000 внутри namespace контейнера).
Иначе broker падает с `AccessDeniedException: /var/lib/kafka/data`.

В compose **не** использовать `0.0.0.0` в `KAFKA_LISTENERS` — Kafka
требует пустой host (`PLAINTEXT://:9092`), иначе
`advertised.listeners cannot use the nonroutable meta-address 0.0.0.0`.

## Health check

```bash
# контейнер (kafka должен быть Up (healthy)):
ansible -i inventory.ini kafka -m ansible.builtin.shell -a 'cd /opt/kafka && docker compose ps'

# брокер отвечает (изнутри):
ansible -i inventory.ini kafka -m ansible.builtin.shell -a 'docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list'

# снаружи (advertised listener):
docker run --rm apache/kafka:3.9.0 /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server <APP_HOST>:9092 | head -2

# консьюмер-группа воркера (лаг по партициям):
ansible -i inventory.ini kafka -m ansible.builtin.shell -a 'docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group ai-meeting-copilot'
```

## Деплой

```bash
ssh -p <SSH_PORT> -i ~/.ssh/deploy_ci deploy@<APP_HOST> kafka
```

Обновление образа = редактирование тега в compose-шаблоне роли
(например `roles/baseline/templates/stacks/kafka-compose.yml.j2`) →
прогон роли → deploy-юнит. Мажорную версию Kafka поднимать только с
офсайтом (совместимость KRaft metadata version).

## Внешний листенер SASL_SSL (9093)

Внешний доступ = TLS + логин/пароль: листенер
`EXTERNAL://<APP_HOST>:9093` (**SASL_SSL**, механизм PLAIN, юзер
`admin`). Внутренний PLAINTEXT :9092 без auth остаётся для воркера и
UI на хосте.

**TLS:** самоподписанный CA (генерируется ролью, срок ~10 лет),
сертификат брокера CN=`<KAFKA_FQDN>` с SAN: адрес хоста, `<KAFKA_FQDN>`,
`kafka`, `localhost`. На брокере — PKCS12 keystore
`/opt/kafka/tls/server.p12` (создаётся ansible'ом из
`vault_kafka_tls_server_p12_b64`, пароль `KAFKA_TLS_KEYSTORE_PASSWORD`
в `/opt/kafka/.env`). Клиентам нужен только публичный CA-корень
**`certs/kafka-ca.pem` (лежит в git, не секрет)**.

JAAS + пароль keystore живут в `/opt/kafka/.env`, генерится ролью из
vault (`vault_kafka_sasl_env_content` = `KAFKA_SASL_JAAS_CONFIG` +
`KAFKA_TLS_KEYSTORE_PASSWORD`). Пароль app-клиента:

```bash
ansible-vault view group_vars/<ENV>/vault.yml | grep -o 'user_admin="[^"]*"' | cut -d'"' -f2
```

Подключение (client.properties для docker-клиента / java с PEM-truststore):

```properties
security.protocol=SASL_SSL
ssl.truststore.type=PEM
ssl.truststore.location=/path/to/kafka-ca.pem
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="<пароль из vault>";
# если подключаетесь не по адресу/CN из SAN сертификата:
ssl.endpoint.identification.algorithm=
```

Проверка: с CA+паролем `kafka-topics.sh --bootstrap-server <APP_HOST>:9093 --command-config client.properties --list` → список топиков; без CA — handshake-ошибка (exit≠0); неверный пароль — `SaslAuthenticationException`.

⚠️ Шифрование включено (TLS), но CA самоподписанный → доверие клиента
= наличие `kafka-ca.pem`. Для публичного доступа понадобится публичный
DNS (выпускать сертификат сразу с нужным CN/SAN; ca.pem тот же).

## Веб-морда Kafka (Kafbat UI, :8181)

- URL: `http://<APP_HOST>:8181`, логин `admin`, пароль =
  `SPRING_SECURITY_USER_PASSWORD` из vault (`vault_kafka_ui_env_content`).
- Юнит `kafka-ui.service`, compose `/opt/kafka-ui/docker-compose.yml`.
  Ходит в брокер по внутреннему PLAINTEXT :9092.
- AUTH_TYPE=LOGIN_FORM; смена пароля = правка vault → прогон роли →
  `systemctl restart kafka-ui`.

## Типовые проблемы

| Симптом | Причина | Лечение |
|---|---|---|
| Restarting (1), `AccessDeniedException .../data` | права на `/opt/kafka/data` | `chown 101000:101000 /opt/kafka/data` (root на хосте) |
| `nonroutable meta-address 0.0.0.0` | `KAFKA_LISTENERS` содержит 0.0.0.0 | исправить на `://:9092` в шаблоне, перерендерить ролью |
| Воркер виснет на join | advertised-адрес не совпадает с хостом | проверить `KAFKA_ADVERTISED_LISTENERS` в `/opt/kafka/docker-compose.yml` |
| Диск `/` заполнен | данные Kafka растут (retention 7d по умолчанию) | `docker exec kafka du -sh /var/lib/kafka/data`; при необходимости задать retention на топик или вынести данные на отдельный LV |
