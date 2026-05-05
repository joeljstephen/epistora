export default function ConversationList({
  conversations,
  activeId,
  collapsed,
  onToggle,
  onNew,
  onOpen,
  onDelete,
}) {
  return (
    <aside className={`conversation-list ${collapsed ? "is-collapsed" : ""}`}>
      <header>
        <button type="button" className="ghost" onClick={onToggle}>
          {collapsed ? "Show" : "Hide"}
        </button>
        {!collapsed ? <button type="button" onClick={onNew}>New</button> : null}
      </header>
      {!collapsed ? (
        <div className="conversation-items">
          {conversations.length === 0 ? <p className="caption">No conversations yet.</p> : null}
          {conversations.map((conversation) => (
            <div className={`conversation-item ${conversation.id === activeId ? "is-active" : ""}`} key={conversation.id}>
              <button type="button" onClick={() => onOpen(conversation.id)}>
                <span>{conversation.title}</span>
                <small>{conversation.message_count || 0} messages</small>
              </button>
              <button type="button" className="icon-button" aria-label="Delete conversation" onClick={() => onDelete(conversation.id)}>
                x
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
