export const config = {
  mock: process.env.MOCK_MODE === "true",
  langHint: process.env.LANG_HINT ?? "auto",
  kafka: {
    brokers: (process.env.KAFKA_BROKERS ?? "kafka:9092").split(","),
    clientId: process.env.KAFKA_CLIENT_ID ?? "meeting-copilot-front",
    groupId: process.env.KAFKA_GROUP_ID ?? "meeting-copilot-front-ui",
    topics: {
      uploaded: process.env.TOPIC_UPLOADED ?? "meetings.uploaded",
      ready: process.env.TOPIC_READY ?? "meetings.ready",
      failed: process.env.TOPIC_FAILED ?? "meetings.failed",
    },
  },
  minio: {
    endPoint: process.env.MINIO_ENDPOINT ?? "minio",
    port: Number(process.env.MINIO_PORT ?? "9000"),
    useSSL: process.env.MINIO_USE_SSL === "true",
    accessKey:
      process.env.MINIO_ACCESS_KEY ?? process.env.MINIO_ROOT_USER ?? "",
    secretKey:
      process.env.MINIO_SECRET_KEY ?? process.env.MINIO_ROOT_PASSWORD ?? "",
    recordingsBucket: process.env.RECORDINGS_BUCKET ?? "recordings",
    resultsBucket: process.env.RESULTS_BUCKET ?? "results",
  },
} as const;
