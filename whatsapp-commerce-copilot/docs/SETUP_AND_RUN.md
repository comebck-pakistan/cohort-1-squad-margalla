# The Ultimate "No-Tech-Background" Setup Guide 🚀

Hey there! If you are reading this, you probably want to run the **WhatsApp Commerce Copilot** on your computer. Don't worry if you don't have a technical background — this guide is written specifically for you! 

If you know how to download a program and open your computer's Terminal (or Command Prompt), you can do this. Let's take it step by step.

---

## 🛠️ Step 1: Download Two Essential Programs

Before we can run the code, your computer needs two helper programs. You only ever have to download these once.

1. **Docker Desktop**
   - **What it is:** A program that safely runs all our backend databases behind the scenes so you don't have to install them manually.
   - **How to get it:** Go to [Docker's Website](https://www.docker.com/products/docker-desktop/), download it for your computer (Mac or Windows), and install it.
   - **Important:** After it installs, **open the Docker application** and leave it running in the background. You'll see a little whale icon at the top of your screen (Mac) or bottom right (Windows).

2. **Node.js**
   - **What it is:** A tool that runs our visual Dashboard website.
   - **How to get it:** Go to the [Node.js Website](https://nodejs.org/en), download the "LTS" (Recommended For Most Users) version, and install it by clicking "Next" through the installer.

---

## 🚀 Step 2: Start the Engine (Backend)

Now we need to open your computer's **Terminal** (on Mac, search for "Terminal" in Spotlight; on Windows, search for "Command Prompt" or "PowerShell" in the Start menu).

1. In your Terminal, navigate to the folder where you downloaded this code. 
   *(Tip: You can type `cd ` and then drag the folder from your files directly into the Terminal window and press Enter!)*
2. Copy and paste this exact command into the Terminal and press Enter:

```bash
docker compose up -d --build
```

**Wait a few minutes!** The first time you run this, your computer will download a bunch of background tools. You will see a lot of text scrolling by. When it stops and says things like "Started" or "Running", you are good to go!

### Optional: Enable LangChain AI

The app can run without an AI key. When you are ready, put these values in the
root `.env` file:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Then apply the change with `docker compose restart backend`. Do not place the
API key in dashboard code or commit it to source control.

---

## 💻 Step 3: Start the Website (Dashboard)

Now we need to start the actual website that you click around on. 

1. **Open a brand new, second Terminal window** (keep the first one open).
2. Just like before, navigate to the project folder, but this time, go one step further into the `dashboard` folder:

```bash
cd dashboard
```

3. Type this command and press Enter (this downloads the website buttons and colors):

```bash
npm install
```

4. Once that finishes, type this command and press Enter to actually start the website:

```bash
npm run dev
```

---

## 🎉 Step 4: You Are Live!

Open your favorite web browser (Chrome, Safari, etc.) and type this into the web address bar at the top:

👉 **[http://localhost:5173/](http://localhost:5173/)**

**Boom!** The dashboard should load right up on your screen.

---

## 📱 Step 5: Connect Your WhatsApp

To make the AI actually talk to your customers, we need to link it to your phone.

1. On the dashboard website you just opened, click on **Conversations** at the top.
2. Look on the left side and click the **Connect WhatsApp** button.
3. A QR code will pop up on your screen.
4. Open the WhatsApp app on your phone, go to **Settings > Linked Devices > Link a Device**, and scan the QR code on your computer screen.

**You are fully set up!** Any messages sent to your WhatsApp will now instantly pop up on the dashboard. Enjoy!

 
