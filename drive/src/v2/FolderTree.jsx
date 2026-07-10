import { useMemo } from "react";
import { listFolderChildren } from "@/driveTree";

const ChevronRight = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <polyline points="9 18 15 12 9 6"/>
  </svg>
);
const ChevronDown = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <polyline points="6 9 12 15 18 9"/>
  </svg>
);
const FolderIcon = ({ open }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {open
      ? <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      : <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    }
  </svg>
);

function TreeNode({ tree, folderId, activeId, depth, onSelect }) {
  const children = useMemo(() => {
    const items = listFolderChildren(tree, folderId);
    return items.filter((c) => c.kind === "folder");
  }, [tree, folderId]);

  if (!children.length && depth === 0) return null;

  return (
    <ul className="rd-v2-folder-tree" role="tree">
      {children.map((folder) => {
        const isActive = folder.id === activeId;
        const isAncestor = activeId.startsWith(folder.id) && folder.id;
        const expanded = isActive || isAncestor;
        return (
          <li key={folder.id || "root-child"} role="none">
            <button
              type="button"
              role="treeitem"
              aria-selected={isActive}
              aria-expanded={expanded}
              className={`rd-v2-folder-node${isActive ? " on" : ""}`}
              style={{ paddingLeft: 8 + depth * 16 }}
              onClick={() => onSelect(folder.id)}
            >
              <span className="rd-v2-folder-glyph">
                {expanded ? <ChevronDown /> : <ChevronRight />}
              </span>
              <FolderIcon open={expanded} />
              {folder.name}
            </button>
            {expanded ? (
              <TreeNode
                tree={tree}
                folderId={folder.id}
                activeId={activeId}
                depth={depth + 1}
                onSelect={onSelect}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function FolderTree({ tree, folderId, onFolderChange }) {
  return (
    <nav className="rd-v2-folder-nav" aria-label="Vault folders">
      <TreeNode tree={tree} folderId="" activeId={folderId || ""} depth={0} onSelect={onFolderChange} />
    </nav>
  );
}
