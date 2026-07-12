import { createRoot } from "react-dom/client";
import "./v2-base.css";
import "./v2.css";
import "./premium.css";
import "./premium-components.css";
import "./premium-profile.css";
import "./premium-fixes.css";
import { V2App } from "./App.jsx";

createRoot(document.getElementById("root")).render(<V2App />);
