export default function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled = false,
  placeholder = "Ask a question",
}) {
  return (
    <form
      className="chat-input"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="chat-input-field">
        <textarea
          value={value}
          rows={2}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
        />
        <span>Enter to send · Shift Enter for newline</span>
      </div>
      <button type="submit" className="primary" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  );
}
