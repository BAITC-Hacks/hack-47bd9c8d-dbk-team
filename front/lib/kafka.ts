import { Kafka, type Producer } from "kafkajs";
import { config } from "./config";
import { setStatus } from "./store";
import type { FailedEvent, ReadyEvent, UploadedEvent } from "./types";

const globalRef = globalThis as unknown as {
  __kafkaProducer?: Producer;
  __kafkaConsumerStarted?: boolean;
};

function getKafka(): Kafka {
  return new Kafka({
    clientId: config.kafka.clientId,
    brokers: config.kafka.brokers,
    retry: { retries: 5 },
  });
}

async function getProducer(): Promise<Producer> {
  if (!globalRef.__kafkaProducer) {
    const producer = getKafka().producer();
    await producer.connect();
    globalRef.__kafkaProducer = producer;
  }
  return globalRef.__kafkaProducer;
}

export async function publishUploaded(event: UploadedEvent): Promise<void> {
  const producer = await getProducer();
  await producer.send({
    topic: config.kafka.topics.uploaded,
    messages: [{ key: event.meeting_id, value: JSON.stringify(event) }],
  });
}

// Started once from instrumentation.ts (Node runtime). Consumes
// meetings.ready / meetings.failed into the in-memory status store.
export async function startEventConsumer(): Promise<void> {
  if (config.mock || globalRef.__kafkaConsumerStarted) return;
  globalRef.__kafkaConsumerStarted = true;

  const consumer = getKafka().consumer({ groupId: config.kafka.groupId });
  await consumer.connect();
  await consumer.subscribe({
    topics: [config.kafka.topics.ready, config.kafka.topics.failed],
  });

  await consumer.run({
    eachMessage: async ({ topic, message }) => {
      const raw = message.value?.toString();
      if (!raw) return;
      try {
        if (topic === config.kafka.topics.ready) {
          const event = JSON.parse(raw) as ReadyEvent;
          setStatus({
            meeting_id: event.meeting_id,
            state: "ready",
            result_key: event.result_key,
          });
        } else if (topic === config.kafka.topics.failed) {
          const event = JSON.parse(raw) as FailedEvent;
          setStatus({
            meeting_id: event.meeting_id,
            state: "failed",
            stage: event.stage,
            error: event.error,
          });
        }
      } catch (err) {
        console.error("[kafka] failed to handle event", topic, err);
      }
    },
  });

  console.log(
    `[kafka] listening: ${config.kafka.topics.ready}, ${config.kafka.topics.failed}`,
  );
}
