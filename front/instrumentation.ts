export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { startEventConsumer } = await import("./lib/kafka");
    startEventConsumer().catch((err) => {
      console.error("[kafka] consumer failed to start", err);
    });
  }
}
