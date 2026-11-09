"use client";
import { Conversation as ElevenConversation, type Conversation } from "@elevenlabs/client";
import { useEffect, useRef, useState } from "react";
import { startManaged, closeManaged } from "./actions";

type Line = { role: string; text: string; id?: number };
export default function ManagedConversation({
  enabled,
  customers,
}: {
  enabled: boolean;
  customers: { id: string; name: string }[];
}) {
  const [customer, setCustomer] = useState(customers[0]?.id || "");
  const [state, setState] = useState("Ready");
  const [active, setActive] = useState(false);
  const [textMode, setTextMode] = useState(true);
  const [message, setMessage] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const conversation = useRef<Conversation | null>(null);
  const evaluation = useRef<string | null>(null);
  const starting = useRef(false);
  function finalize() {
    if (evaluation.current) {
      void closeManaged(evaluation.current);
      evaluation.current = null;
    }
    setActive(false);
    starting.current = false;
  }
  async function end() {
    await conversation.current?.endSession();
    conversation.current = null;
    finalize();
    setState("Ended. Refresh to inspect the saved outcome.");
  }
  useEffect(
    () => () => {
      void conversation.current?.endSession();
    },
    [],
  );
  async function begin(textOnly: boolean) {
    if (starting.current || active) return;
    starting.current = true;
    setActive(true);
    setState("Connecting…");
    setLines([]);
    setTextMode(textOnly);
    try {
      const result = await startManaged(customer, textOnly);
      if (result.error || !result.url || !result.token)
        throw new Error(result.error || "Could not connect");
      evaluation.current = result.id || null;
      conversation.current = await ElevenConversation.startSession({
        signedUrl: result.url,
        connectionType: "websocket",
        textOnly,
        overrides: { conversation: { textOnly } },
        dynamicVariables: {
          customer_name: result.customerName || "",
          secret__session_token: result.token,
        },
        onConnect: () =>
          setState(textOnly ? "Connected · text evaluation" : "Connected · microphone on"),
        onMessage: ({ role, message, event_id }) =>
          setLines((current) => {
            const next = { role: role === "agent" ? "Alex" : "You", text: message, id: event_id };
            return current.some((line) => line.id === event_id)
              ? current.map((line) => (line.id === event_id ? next : line))
              : [...current, next];
          }),
        onModeChange: ({ mode }) => {
          if (!textOnly)
            setState(mode === "speaking" ? "Alex is speaking · you can interrupt" : "Listening");
        },
        onError: () =>
          setState("The managed connection reported a problem. No phone call was placed."),
        onDisconnect: () => {
          conversation.current = null;
          finalize();
          setState("Session ended. Refresh to inspect its saved outcome.");
        },
      });
    } catch (error) {
      finalize();
      setState(error instanceof Error ? error.message : "Connection unavailable");
    }
  }
  function send(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() || !conversation.current) return;
    conversation.current.sendUserMessage(message);
    setLines((l) => [...l, { role: "You", text: message }]);
    setMessage("");
  }
  return (
    <div>
      <label htmlFor="managed-customer">Fictional customer</label>
      <select
        id="managed-customer"
        disabled={active}
        value={customer}
        onChange={(e) => setCustomer(e.target.value)}
      >
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <div className="customer-actions" style={{ marginTop: 16 }}>
        <button className="button" disabled={!enabled || active} onClick={() => void begin(false)}>
          Start voice conversation
        </button>
        <button className="button" disabled={!enabled || active} onClick={() => void begin(true)}>
          Check booking in text
        </button>
        <button className="button" disabled={!active} onClick={() => void end()}>
          End session
        </button>
      </div>
      <p role="status">{enabled ? state : "The managed candidate is not available yet."}</p>
      <div aria-live="polite" aria-label="Conversation transcript">
        {lines.map((line, i) => (
          <p key={i}>
            <strong>{line.role}: </strong>
            {line.text}
          </p>
        ))}
      </div>
      {active && textMode && (
        <form onSubmit={send}>
          <label htmlFor="managed-message">Your reply</label>
          <input
            id="managed-message"
            value={message}
            maxLength={2000}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button className="button" type="submit">
            Send reply
          </button>
        </form>
      )}
    </div>
  );
}
