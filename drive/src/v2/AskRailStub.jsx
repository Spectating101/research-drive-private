export function AskRailStub({ dataset, searchQuery, mainTab }) {
  const ctx = dataset?.dataset_id
    ? `Context: ${dataset.dataset_id}`
    : dataset?.title
      ? `Context: ${dataset.title}`
      : "No dataset selected";
  const tab = mainTab ? ` · ${mainTab}` : "";
  const q = searchQuery ? ` · search: ${searchQuery}` : "";
  return (
    <>
      <p className="rd-v2-ask-ctx">
        {ctx}
        {tab}
        {q}
      </p>
      <div className="rd-v2-ask-bubble">
        <strong>You:</strong> overlap with ticker_week before 2020?
      </div>
      <div className="rd-v2-ask-bubble agent">
        <strong>Agent:</strong> 82% date overlap. TW missing pre-2019.
      </div>
      <div className="rd-v2-ask-input">
        <textarea placeholder="Message… Ask uses catalog + MCP tools" readOnly />
      </div>
    </>
  );
}
