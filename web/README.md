# The Jobs page (`web/`)

Plain JavaScript modules and CSS, no build step. Served at `/jobs/` by the home dashboard or by `jobboard serve`
(both through `jobboard/http_routes.py`): `index.html`, and any `.js` / `.css` file under `js/`, `css/` or
`vendor/`. `vendor/icons.js` is a copy of the dashboard's shared icons, for `jobboard serve`.

```
web/
  index.html            loads css/main.css and js/main.js
  js/
    main.js             starts the App
    core/               the plumbing (no screens here)
      app.js            App: owns everything, the only place state changes — start reading here
      store.js          Store: what the page knows (jobs, the open job, filters, busy flags)
      api.js            ApiClient: every call to the engine
      component.js      Component: the base class for every screen and piece
      dom.js            h() to build elements, bem() for class names, icon()
      format.js         pay, dates, places as text (no DOM; unit tested in Node)
      constants.js      fixed lists and labels (statuses, filters, screens)
      dialog.js         Dialog: the one pop-up
      toast.js          Toast: the message at the bottom
      keyboard.js       KeyboardShortcuts: j/k/s/x/a/?
    components/         pieces used on screens (job card, job detail and its tabs, sidebar, dialogs, widgets)
    screens/            one class per screen: matches, applications, profile, boards, coach
  css/
    main.css            imports everything, in order
    base/               tokens.css (every colour and size), reset.css, utilities.css (u-*)
    blocks/             one file per BEM block, named after the block (job-card.css styles .job-card)
  tests/
    *.test.mjs          unit tests:   node --test web/tests/*.test.mjs   (or ./dev test)
    smoke.browser.mjs   clicks through every screen in a headless browser (./dev browser)
```

## How it works

1. Something happens (a click, a key) and calls an **App** method, like `app.pick(id)` or `app.saveJob(job)`.
2. The App calls the engine through **ApiClient**, updates the **Store**, then calls `render()`.
3. `render()` asks the current screen for its elements. Screens and components only *read* the store and
   call App methods; they never change the store themselves (the one exception is small UI state in
   `store.ui`, like which tab is open).

## Naming: BEM

Every class is `block`, `block__element` or `block--modifier` (or `block__element--modifier`).

* A **block** is a stand-alone piece: `job-card`, `panel`, `button`, `tabs`.
* An **element** is a part that only makes sense inside its block: `job-card__title`, `tabs__tab`.
* A **modifier** is a variant or state: `button--primary`, `job-card--active`, `tabs__tab--active`.
* Utilities start with `u-` and do one thing: `u-muted`, `u-sr-only`, `u-hide-phone`.
* Never style by tag inside a block (`.panel p` is the rare exception for plain text), and never nest
  blocks' selectors more than one level.

In JavaScript use `bem()` so names can't drift:

```js
bem("job-card")                              // "job-card"
bem("job-card", "title")                     // "job-card__title"
bem("tabs", "tab", { active: isOpen })       // "tabs__tab tabs__tab--active" when isOpen
```

`./dev browser` fails if the page uses a class that has no style, which catches typos between `js/` and `css/`.

## Common changes

* **Change a colour or size everywhere:** `css/base/tokens.css`.
* **Change a label** (status names, filter chips): `js/core/constants.js`.
* **Add a block:** make `css/blocks/your-block.css` (only `.your-block…` selectors in it), add it to
  `css/main.css`, and use `bem("your-block", …)` in the JavaScript.
* **Add a tab to the open job:** write a panel class in `js/components/job-panels.js` (with `render(job)`),
  register it in `JobDetail.panels` and `JobDetail.tabs()` in `js/components/job-detail.js`.
* **Add a screen:** a class in `js/screens/` extending `Component`, register it in `App.screens`
  (`js/core/app.js`) and add it to `SCREENS` in `js/core/constants.js`.
* **Call a new engine action:** `app.api.act("action_name", data)`; the action must exist in `ACTIONS` in
  `jobboard/api.py`.

Always run `./dev check` after a change. It runs every test and clicks through the page.
