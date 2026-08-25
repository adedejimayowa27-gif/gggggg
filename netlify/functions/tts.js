// This runs on Netlify's server, never in the browser —
// so the API key here is never visible to anyone visiting the site.

export default async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const apiKey = process.env.FISH_API_KEY;
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "Server is missing FISH_API_KEY. Set it in Netlify env vars." }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  let payload;
  try {
    payload = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid request body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const text = (payload.text || "").trim();
  if (!text) {
    return new Response(JSON.stringify({ error: "No text provided" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (text.length > 2000) {
    return new Response(
      JSON.stringify({ error: "Text too long for a single request (max 2000 characters). Split it up." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  // Optional: a saved voice ID from your Fish Audio account.
  // If none is set, Fish Audio uses its default voice for the model.
  const referenceId = payload.reference_id || process.env.FISH_DEFAULT_VOICE_ID || undefined;

  const body = {
    text,
    format: "mp3",
    prosody: {
      speed: payload.speed || 1,
    },
    ...(referenceId ? { reference_id: referenceId } : {}),
  };

  try {
    const fishRes = await fetch("https://api.fish.audio/v1/tts", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        model: "s2.1-pro-free",
      },
      body: JSON.stringify(body),
    });

    if (!fishRes.ok) {
      const errText = await fishRes.text();
      return new Response(
        JSON.stringify({ error: `Fish Audio error (${fishRes.status})`, detail: errText }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }

    const audioBuffer = await fishRes.arrayBuffer();
    return new Response(audioBuffer, {
      status: 200,
      headers: {
        "Content-Type": "audio/mpeg",
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: "Request to Fish Audio failed", detail: String(err) }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
};

export const config = {
  path: "/.netlify/functions/tts",
};
