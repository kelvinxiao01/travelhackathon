// Deno DRL configuration
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

Deno.serve(async (req: Request) => {
  // Reject non-POST requests
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { 
      status: 405, 
      headers: { "Content-Type": "text/plain" } 
    });
  }

  try {
    const payload = await req.json();
    console.log("Supabase Edge Function received webhook payload:", JSON.stringify(payload, null, 2));

    const data = payload.data;
    if (!data || data.event_type !== "message.received") {
      console.log(`Ignoring unsupported event type: ${data?.event_type}`);
      return new Response(JSON.stringify({ status: "ignored" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    const msgPayload = data.payload;
    if (!msgPayload) {
      throw new Error("Missing message payload inside event.");
    }

    const fromNumber = msgPayload.from?.phone_number;
    const toNumber = msgPayload.to?.[0]?.phone_number;
    const text = msgPayload.text;

    // Check backend URL from Deno environment
    const backendUrl = Deno.env.get("ROAM_BACKEND_URL") || "http://localhost:8000";
    const backendSecret = Deno.env.get("ROAM_BACKEND_SECRET") || "";

    console.log(`Routing incoming text from ${fromNumber} to backend: ${backendUrl}/api/webhooks/sms`);

    // Asynchronously forward the payload to the backend using fire-and-forget
    // We catch errors to avoid failing the webhook acknowledgement
    fetch(`${backendUrl.replace(/\/$/, "")}/api/webhooks/sms`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Roam-Secret": backendSecret
      },
      body: JSON.stringify({
        from_number: fromNumber,
        to_number: toNumber,
        text: text
      })
    })
    .then(async (res) => {
      console.log(`Backend forwarded response: ${res.status} ${await res.text()}`);
    })
    .catch((err) => {
      console.error("Failed to forward SMS payload to backend:", err);
    });

    // Immediately respond to Telnyx with HTTP 200 to acknowledge delivery
    return new Response(JSON.stringify({ status: "accepted" }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Connection": "keep-alive"
      }
    });

  } catch (error) {
    console.error("Error processing incoming webhook:", error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 400,
      headers: { "Content-Type": "application/json" }
    });
  }
});
