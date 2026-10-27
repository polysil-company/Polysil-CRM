# Testing the Android app with Maestro

[Maestro](https://maestro.dev) drives a real Android phone over USB, the way a person would, and reports what passed. These flows check the Polysil app (`com.polysil.crm`, TRK-008):

- **Smoke tests:** it opens, signs in and moves around.
- **Duty tests:** location tracking works, including while the app is closed.

**Prompt for a testing agent:** read this file and follow it top to bottom on the connected phone. Report in the format at the end. Don't change app code. Ask the person only if the phone or a credential is missing.

## Rules

- **Credentials:** never write a password into a file, a screenshot name or the report. Pass them with `-e`.
- **Smoke tests** (`--include-tags smoke`) only read data, so they are safe on the client's app (`https://crm.polysilirrigation.com`).
- **Duty tests** (`--include-tags duty`) start and end a real duty for the signed-in account. Run them with a **test staff account** whose role tracks, such as a field officer, never a real employee's account. Better still, run them on an APK built for the test site (see "Which APK").
- Never message or call a real customer from the app.

## 1. Set up the computer (Windows, one time)

1. **Java 17 or later** is needed. This PC already has it at `E:\Installed\JDK17`. In PowerShell:
   ```
   setx JAVA_HOME "E:\Installed\JDK17"
   setx PATH "$env:PATH;E:\Installed\JDK17\bin"
   ```
   Open a new PowerShell window and check with `java -version`.
2. **adb** comes with Android Studio's SDK: `%LOCALAPPDATA%\Android\Sdk\platform-tools`. Add it to `PATH` the same way, then check with `adb version`.
3. **Maestro:**
   - download `maestro.zip` from the latest release at https://github.com/mobile-dev-inc/maestro/releases;
   - unzip it to `C:\maestro`;
   - add `C:\maestro\maestro\bin` to `PATH`;
   - check in a new window with `maestro --version`.
   - If the native Windows build gives trouble, use WSL2 with `curl -fsSL "https://get.maestro.mobile.dev" | bash`.

## 2. Connect the phone

1. On the phone, open **Settings → About phone** and tap **Build number** 7 times. Then go to **Developer options** and turn on **USB debugging**.
2. Connect it by USB and accept "Allow USB debugging?" on the phone.
3. Run `adb devices`. The phone must show as `device`, not `unauthorized`.
4. Install the APK: `adb install -r polysil-tracking-<version>.apk`. The flows don't install it.
5. Keep the phone unlocked, with the screen on and GPS on, for the smoke and setup flows.

### Which APK

- **The client's app:** the APK from **Actions → Android APK** with `server-url` set to `https://crm.polysilirrigation.com`. Run the smoke tests on it.
- **The test site:** the same workflow with `server-url` set to the test site's address (ask the developer). Run everything on it, duty tests included.

## 3. Run

From the repository root, in PowerShell. Put the test account in variables first, so it stays out of the command history:

```
$env:MAESTRO_EMAIL = "test.officer@…"; $env:MAESTRO_PASSWORD = "…"
```

**Smoke tests (about 3 minutes):**

```
maestro test mobile\maestro\flows --include-tags smoke -e STAFF_EMAIL=$env:MAESTRO_EMAIL -e STAFF_PASSWORD=$env:MAESTRO_PASSWORD --format junit --output maestro-smoke.xml --test-output-dir maestro-output
```

**Duty tests (about 15 minutes, with a wait in the middle):**

```
maestro test mobile\maestro\flows\04-duty-setup.yaml -e STAFF_EMAIL=$env:MAESTRO_EMAIL -e STAFF_PASSWORD=$env:MAESTRO_PASSWORD --test-output-dir maestro-output
maestro test mobile\maestro\flows\05-duty-on.yaml -e STAFF_EMAIL=$env:MAESTRO_EMAIL -e STAFF_PASSWORD=$env:MAESTRO_PASSWORD --test-output-dir maestro-output
```

Now **lock the phone and wait 10 minutes**. The person carrying it should walk at least 200 m, or use a mock-location app with a route. Then:

```
maestro test mobile\maestro\flows\06-duty-uploaded.yaml -e STAFF_EMAIL=$env:MAESTRO_EMAIL -e STAFF_PASSWORD=$env:MAESTRO_PASSWORD --test-output-dir maestro-output
maestro test mobile\maestro\flows\07-duty-off.yaml -e STAFF_EMAIL=$env:MAESTRO_EMAIL -e STAFF_PASSWORD=$env:MAESTRO_PASSWORD --test-output-dir maestro-output
```

Finally, on a computer, open **Team map → the test account → today**. The route should show the walk, with km.

If a step can't find something on screen, run `maestro studio` (or `maestro hierarchy`) to see what Maestro sees, and note it in the report.

### An agent driving the phone directly (optional)

`maestro mcp` gives an AI agent such as Claude Code tools to see the screen, tap and run flows. Add it as an MCP server (`claude mcp add maestro -- maestro mcp`), connect the phone as above, and ask the agent to run the steps in this file.

## What each flow checks

| Flow               | Tag   | Checks                                                                                               |
| ------------------ | ----- | ---------------------------------------------------------------------------------------------------- |
| `01-launch`        | smoke | Opens on sign-in with the Polysil logo and "CRM & DMS"                                               |
| `02-sign-in`       | smoke | Staff email sign-in lands on the Dashboard                                                           |
| `03-menu-pages`    | smoke | Leads, Quotations, Sales orders, Tasks and Visits open from the menu                                 |
| `04-duty-setup`    | duty  | Consent, then location "Allow all the time", battery unrestricted, notifications; no setup card left |
| `05-duty-on`       | duty  | **Go on duty** shows "On duty since …"; the app goes to the background                               |
| `06-duty-uploaded` | duty  | After 10 minutes closed: a last upload exists, and nothing waits for sign-in (TRK-009 device token)  |
| `07-duty-off`      | duty  | **Go off duty** shows "Off duty: your route isn't recorded."                                         |
| `08-sign-out`      | smoke | Sign out returns to sign-in                                                                          |

Screenshots of each step are saved in `maestro-output`.

## Known limits

- **Web pages in the app:** the screens are the web app inside Android's WebView. On WebView 150 and later, Maestro can't find text boxes by their name, so the flows tap each box's label, which focuses it.
- **Release builds** can't use `androidWebViewHierarchy: devtools`, because WebView debugging is off. The flows don't need it.
- **Phone settings** ("Allow all the time", battery) are Android screens whose wording differs by brand and Android version.
  - If `04-duty-setup` can't tap them, set them by hand and run it again; it then checks they're set.
  - On Xiaomi, Vivo or Oppo, also turn on **Autostart** by hand. No flow can check it.

## Report back in this format

```
Phone: <brand model>, Android <version>, WebView <version>
App: <APK name and version>, server <url>
Account role: <role> (no credentials)

| Flow | Result | Note |
|---|---|---|
| 01-launch | ✅/❌ | … |
…

Failures: for each one, the step that failed, what was on screen (attach the screenshot from maestro-output) and what you expected.
Route check: km on Team map vs the real walk.
```
