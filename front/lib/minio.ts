import * as Minio from "minio";
import { config } from "./config";

const globalRef = globalThis as unknown as { __minioClient?: Minio.Client };

export function getMinio(): Minio.Client {
  if (!globalRef.__minioClient) {
    globalRef.__minioClient = new Minio.Client({
      endPoint: config.minio.endPoint,
      port: config.minio.port,
      useSSL: config.minio.useSSL,
      accessKey: config.minio.accessKey,
      secretKey: config.minio.secretKey,
    });
  }
  return globalRef.__minioClient;
}

export async function ensureBucket(bucket: string): Promise<void> {
  const client = getMinio();
  const exists = await client.bucketExists(bucket).catch(() => false);
  if (!exists) {
    await client.makeBucket(bucket);
  }
}

export async function putRecording(
  objectKey: string,
  data: Buffer,
  contentType: string,
): Promise<void> {
  await ensureBucket(config.minio.recordingsBucket);
  await getMinio().putObject(
    config.minio.recordingsBucket,
    objectKey,
    data,
    data.length,
    { "Content-Type": contentType },
  );
}

export async function statResult(
  resultKey: string,
): Promise<Minio.BucketItemStat | null> {
  try {
    return await getMinio().statObject(config.minio.resultsBucket, resultKey);
  } catch {
    return null;
  }
}

export async function getResultJson<T>(resultKey: string): Promise<T> {
  const stream = await getMinio().getObject(
    config.minio.resultsBucket,
    resultKey,
  );
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf-8")) as T;
}
