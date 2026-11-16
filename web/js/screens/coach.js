// Coach: the job-search copilot, about your whole search.
import { Component } from "../core/component.js";
import { h } from "../core/dom.js";
import { button, chatLog, emptyState, spinner } from "../components/widgets.js";

const SUGGESTIONS = ["Which of my matches should I apply to first?", "What skills should I learn next?", "Help me answer \"tell me about yourself\"", "How do I negotiate an offer?", "Write a LinkedIn message to a recruiter"];

export class CoachScreen extends Component {
  render() {
    const store = this.store;
    const input = h("input", { class: "ask-box__input", id: "coach-question", placeholder: "Ask anything about your search", "aria-label": "Ask Coach", onkeydown: (e) => { if (e.key === "Enter") send(); } });
    const send = async (text) => {
      const q = (text || input.value).trim();
      if (!q || store.busy.coach) return;
      input.value = "";
      store.chat.push({ role: "user", content: q });
      store.busy.coach = true;
      this.app.render();
      try {
        const out = await this.api.act("ask", { q });
        store.chat.push({ role: "assistant", content: out.answer });
      } catch (e) { store.chat.pop(); this.app.toast.error(e); } finally { store.busy.coach = false; this.app.render(); }
    };
    return [
      h("header", { class: "page-header" },
        h("div", { class: "page-header__titles" }, h("h1", { class: "page-header__title" }, "Coach"), h("p", { class: "page-header__subtitle" }, "Your job-search copilot, running on this server")),
        h("div", { class: "page-header__actions" },
          store.chat.length ? button("New chat", async () => { await this.api.act("chat_clear", {}); store.chat = []; this.app.render(); }, { kind: "ghost" }) : null)),
      h("div", { class: "coach" },
        !store.chat.length ? emptyState({ iconName: "bolt", title: "Hi, I'm your coach", text: "I know your profile, your matches and how your applications are going. Ask me to plan your week, prep you for an interview, or help with a message." }) : null,
        chatLog(store.chat),
        this.busy("coach") ? h("div", { class: "working" }, spinner(), "Thinking… the local model takes a little while.") : null,
        !store.chat.length ? h("div", { class: "chip-list u-center" }, SUGGESTIONS.map((s) => h("button", { class: "chip", type: "button", onclick: () => send(s) }, s))) : null,
        h("div", { class: "ask-box" }, input, button("Send", () => send(), { kind: "primary", disabled: this.busy("coach") })))];
  }
}
