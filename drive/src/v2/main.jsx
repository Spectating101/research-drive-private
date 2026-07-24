import { createRoot } from "react-dom/client";
import "./v2-base.css";
import "./v2.css";
import "./premium.css";
import "./premium-components.css";
import "./premium-profile.css";
import "./premium-synthesis.css";
import "./premium-fixes.css";
import "./synthesis-s04-review.css";
import "./release-visual.css";
import "./release-mobile-fixes.css";
import "./interaction-guidance.css";
import "./interaction-feedback.css";
import "./decoration-layer.css";
import "./release-scale.css"; /* last: laptop/desktop resolution ladder + rail collapse */
import { InteractionProvider } from "./InteractionGuidance.jsx";
import { V2App } from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <InteractionProvider>
    <V2App />
  </InteractionProvider>,
);
