// Start the Jobs page. Read core/app.js next: it explains how the page is put together.
import { App } from "./core/app.js";

const app = new App({ root: document.getElementById("app"), toastEl: document.getElementById("toast"), dialogEl: document.getElementById("dialog") });
app.start();
