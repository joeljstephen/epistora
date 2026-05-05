const PROMPTS = [
  "What are the main topics in my knowledge base?",
  "Summarize my recent saves",
  "What connections exist between my sources?",
  "Find sources about my most common topic",
  "What are the key entities across my vault?",
  "Where do my notes disagree or leave gaps?",
];

export default function SuggestedPrompts({ onPick }) {
  return (
    <div className="suggested-prompts">
      {PROMPTS.map((prompt) => (
        <button type="button" key={prompt} onClick={() => onPick(prompt)}>
          {prompt}
        </button>
      ))}
    </div>
  );
}
