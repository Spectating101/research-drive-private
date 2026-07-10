import { useMemo } from "react";
import { homeSuggestedPrompts } from "@/v2/homePrompts";
import { Chip, ChipRow } from "@/v2/ui";

export function HomeSuggestedAsks({ profile, onAskComposer }) {
  const prompts = useMemo(() => homeSuggestedPrompts(profile, { limit: 4 }), [profile]);
  const lead =
    profile && !profile.unknown
      ? "Suggested for your research profile"
      : "Suggested asks — sign in with @yzu.edu.tw for profile-ranked prompts";

  return (
    <section className="rd-v2-home-suggested" aria-label="Suggested asks">
      <p className="muted small rd-v2-home-suggested-lead">{lead}</p>
      <ChipRow>
        {prompts.map((prompt) => (
          <Chip key={prompt} active onClick={() => onAskComposer?.(prompt)}>
            {prompt.length > 72 ? `${prompt.slice(0, 69)}…` : prompt}
          </Chip>
        ))}
      </ChipRow>
    </section>
  );
}
