# AI Prompts

## Setup

**Prompt 1:**

> unzip data.zip and make copy of campus_customs.db called campus_customs_new.db in data folder. make sure original stays unchanged. zip located in "C:\Users\ThinkPad\Downloads"  name is "data (2)" most recent download

**Prompt 2:**

> create AI_prompts.md and save all prompts i send you. for agents use only gpt-6-luna through Portkey. dont change original database, work with campus_customs_new.db. we'll do problems one by one.

**Prompt 3:**

> create AI_prompts.md and keep updating it as we go. make separate section for each problem with problem number and title, prompt i used, and follow up prompt if any with one sentence explaining what was missing. log my actual prompts, dont rewrite them. for all agents use only gpt-6-luna through Portkey.

## Problem 1: Analyze Database and Open Tickets

**Prompt:**

> analyze all tables and fields in campus_customs.db and figure out how 3 open tickets connect to other tables. make working copy campus_customs_new.db and keep original unchanged.

## Problem 2: Harness Table Reference

**Prompt:**

> create output/harness.md and for each database table list all fields and short explanation why table matters for agents. we'll add more to this file later.

## Problem 3: MCP Server with Ticket Tools

**Prompt:**

> problem 3: build MCP server using FastMCP in mcp_server folder, connected to campus_customs_new.db. add 3 tools needed to handle tickets in database. use only actual data from db, dont make up anything. no need to run server yet.

**Follow-up prompt:**

> problem 3: update output/harness.md with 3 MCP tools. for each list which tables it reads, which ticket (101, 102 or 103) it helps and one sentence explaining why that tool is needed for that ticket. also create mcp_server/README.md explaining what server does, database it uses and 3 tools.

*What was missing:* The first prompt built the tools but didn't ask for documentation of which tables each tool reads and which tickets it helps, or for a README for the server.

## Problem 4: Connect MCP Server to Claude Code

**Prompt:**

> problem 4: connect MCP server we built to Claude Code so you can call its tools. save connection config in .mcp.json in project root.

**Follow-up prompt:**

> what does reload claude code mean

*What was missing:* The answer said to reload Claude Code but didn't explain what that means or how to do it.

**Follow-up prompt:**

> clear cache thing?

*What was missing:* The reload steps didn't say which of the several "Reload" options in the command list to pick.

**Follow-up prompt:**

> alright i did it but it didnt asked about campus customs

*What was missing:* The instructions didn't say the approval popup may not appear and didn't give a way to confirm the connection without it.

**Follow-up prompt:**

> problem 4: test all 3 MCP tools we connected. check outputs match campus_customs_new.db and save results in output/mcp_smoke.json. for each tool include prompt i used, tool name and actual output.

*What was missing:* Only `list_open_tickets` had been tried inside Claude Code; the other two tools were never called, outputs weren't checked against the database, and no results were saved.

## Problem 5: Multi-Agent Team with PydanticAI

**Prompt:**

> problem 5: build 5 agents using PydanticAI: Boss, Inventory, Accounting, Facilities and Customer Service. each should have its own role and detailed instructions based on shop rules. agents should be able to communicate and delegate tasks to each other, with full connectivity and agent loops. save prompts separately in backend/prompts, data types in backend/models.py and agent code in backend. use only gpt-6-luna through Portkey API for all agents.

**Follow-up prompt:**

> whats shopp rules

*What was missing:* The prompt asked for instructions "based on shop rules" but there was no shop rules document in the project, so the source of the rules wasn't defined.

**Follow-up prompt:**

> i dont wanna run anything myself why?

*What was missing:* The answer ended with instructions for running the agents manually, even though the run had already been done and only the results needed saving.

**Follow-up prompt:**

> add any missing MCP tools so agents can handle open tickets. make sure all database access goes through MCP, no separate db access. log each agent step in output/audit_trail.json and keep previous records. update output/harness.md with all agents, MCP tools and tables they use. also add safety rules for payments requiring human approval, no contacting real customers or vendors, and limiting token usage. update mcp_server/README.md with new tools.

*What was missing:* The agents read the database directly instead of through MCP, had no audit log, and the safety rules for payments, outside contact and token limits weren't stated or enforced.

## Problem 6: Desk Tickets Page

**Prompt:**

> problem 6: create output/desk_tickets.html that i can open in browser. add tabs for tickets 101, 102, 103 plus Cash and Reflection. check database and write what we expect agents to do for each ticket in Expected section. leave space for Actual results later. keep Cash and Reflection empty for now. dont build backend yet.

**Follow-up prompt:**

> for problem 6, update Expected section for each ticket 101, 102 and 103. explain which agent Boss should call first and why, how agents should delegate work to each other and which MCP tools they'll need. only involve agents actually needed for each ticket, dont send everyone to every ticket. leave Actual section empty for now.

*What was missing:* The Expected sections listed steps but didn't say which agent the Boss calls first and why, how agents hand work to each other, which MCP tools each one needs, or which agents should stay out of each ticket.

**Follow-up prompt:**

> ok change it and then

*What was missing:* The Boss and specialist prompts still used the old routing, sending every specialist to every ticket, so they didn't match the delegation plan on the Expected page.

## Problem 7: FastAPI Desk Backend with Human Approvals

**Prompt:**

> problem 7: build backend/main.py using FastAPI. add routes to get all 3 tickets and their status, run agents for specific ticket, get recent agent activity including messages and tools used, approve payments or purchases only after human approval, get current checking balance from database and reset database to original values. make sure agents cant approve payments themselves or make cash balance negative.

**Follow-up prompt:**

> start backend server from backend folder using uvicorn main --reload --port 8000 and check if it works. also update output/harness.md with all backend routes, their URLs and one line explaining what each does.

*What was missing:* The server hadn't been started the normal way on port 8000, and the harness listed routes without full URLs or how to start the server.

**Follow-up prompt:**

> terminal didnt work though

*What was missing:* The start command assumed `uvicorn` was on PATH and didn't say to run it from the `backend` folder, so it failed in a normal PowerShell terminal opened in `hw5`.

**Follow-up prompt:**

> i paste it and it only pastes as м why?

*What was missing:* The instructions didn't mention that pasting into the PowerShell terminal can fail with a non-English keyboard layout active, or give another way to paste.

**Follow-up prompt:**

> doesnt work

*What was missing:* The answer didn't make clear that the backend was already running and didn't need to be started from the terminal.

**Follow-up prompt:**

> i cant paste it it pastes as м

*What was missing:* The fixes still depended on pasting a long command, which the keyboard layout kept breaking, so a short way to start the server without pasting was needed.

**Follow-up prompt:**

> ctrl c just adds c

*What was missing:* The real cause was never found: the terminal's old PSReadLine 2.0.0 types Ctrl+key shortcuts as letters when a non-English layout is on. So neither Ctrl+V nor Ctrl+C worked, and no working way to stop the server was given.

**Follow-up prompt:**

> its eng

*What was missing:* The server had been stopped so the user could start it, but starting it from the terminal kept failing, so the docs page showed "connection refused". The server should just be started for the user.

**Follow-up prompt:**

> still doesnt work

*What was missing:* The underlying problems were never fixed. The Python Scripts folder wasn't on PATH, so `uvicorn` wasn't recognized. PSReadLine 2.0.0 broke paste. And VS Code terminals opened in `hw5` instead of `backend`.

**Follow-up prompt:**

> is it normal?

*What was missing:* The PSReadLine update didn't warn that a new terminal would ask once whether to trust Microsoft's signed files, or say which answer to pick.

**Follow-up prompt:**

> now its not its eng also look at terminal not just keyboard

*What was missing:* The prompt wasn't really about the keyboard. PowerShell's default Restricted policy blocked the updated PSReadLine, so the user's script policy needed to be set to RemoteSigned.

**Follow-up prompt:**

> u mean ctrl J not +

*What was missing:* The steps said "click +" without saying where that button is or giving a keyboard shortcut for opening a new terminal.

## Problem 8: React Dashboard

**Prompt:**

> problem 8: build frontend dashboard using React, Vite and TypeScript in frontend folder. connect it to backend from problem 7. show all 3 tickets, let me select ticket and run agents, see what each agent is doing and saying during run, mark tickets resolved when finished and show summary of each agent's work. add buttons for human approval of payments and purchases, and show checking balance that updates after payments. make dashboard look professional and easy to use.

**Follow-up prompt:**

> wjat do you mean waiting for you

*What was missing:* The answer said approvals were "waiting for you" without explaining that they are payment requests only a person can approve, where to find them, or what happens if they're left alone.

**Follow-up prompt:**

> approved

*What was missing:* Nothing had actually been approved yet. The user's go-ahead had to be carried out: approve #1 and #2, and reject the redundant #3.

**Follow-up prompt:**

> problem 8: connect frontend to backend at http://localhost:8000 and allow requests from http://localhost:5173. start frontend using npm run dev and check if everything works. also create output/design.md explaining dashboard layout, how agents are visually different, how resolved tickets and cash balance are shown and what creative design choices we made to make it user friendly.

*What was missing:* The dashboard reached the backend through a Vite proxy instead of calling http://localhost:8000 directly. It hadn't been started with plain `npm run dev` and checked end to end. And no design document explained its layout and choices.

## Problem 9: Run All Tickets and Record Actual Results

**Prompt:**

> problem 9: reset campus_customs_new.db to original data and record starting checking balance. then run all 3 tickets (101, 102, 103) through dashboard until resolved. if any payment needs approval ask me first. update Actual section in output/desk_tickets.html with agents involved, their delegations and MCP tools they used based on what actually happened. keep Expected sections unchanged.

**Follow-up prompt:**

> update Cash tab in output/desk_tickets.html with starting checking balance, cash changes for each ticket including payments or purchases and amounts, and ending balance. make sure ending balance matches cash_accounts in database. also create output/resolved_tickets.json with ticket id, final status, short outcome, what each agent did and human approvals. create output/resolved_board.html with screenshots of dashboard for all 3 resolved tickets. append actual runs to audit_trail.json and finish output/harness.md covering tables, tools, agents, routes, dashboard and safety rules. use actual results dont make up data.

*What was missing:* The first prompt didn't ask for the cash reconciliation, a machine-readable record of the resolved tickets, dashboard screenshots, or a final pass on the audit trail and harness.

## Problem 10: Reflection

**Prompt:**

> problem 10: fill Reflection tab in output/desk_tickets.html. evaluate how agents performed on each ticket and why, compare actual results with expected plans for all 3 tickets. explain which tasks could have been simpler with one agent using tools instead of multiple agents and why. also give 3 new problems Campus Customs could solve with our existing agents and tools, and 3 problems it couldnt solve, explaining what additional agents and tools would be needed. make it detailed and based on actual results from our runs, not made up.

**Follow-up prompt:**

> problem 10: make sure all reflection answers are specific to our Campus Customs app and tickets 101, 102 and 103. use actual results from ticket tabs and Cash tab as evidence, including agent actions, delegations, payments and differences from expected plans. avoid generic explanations or made up details.

*What was missing:* Some parts of the first reflection were general (e.g. the "when multiple agents are worth it" list) and didn't point to where in the ticket tabs or Cash tab each claim could be checked.

## Problem 11: Publish to GitHub

**Prompt:**

> problem 11: prepare project for GitHub and check all required files and folders are there. include both database files, requirements.txt, .env.example, .mcp.json and all output files. make sure .gitignore excludes real .env, API keys and unnecessary files. create README explaining how to reset database, start MCP server, FastAPI backend and React dashboard. check no secrets are exposed, then push everything to public GitHub repo and save repo link in output/github_url.txt. give me link so i can submit it on Canvas.

**Follow-up prompt:**

> why claude is the owner weirdo. remove it

*What was missing:* The commit message ended with a "Co-Authored-By: Claude" line, so GitHub listed Claude as a contributor. The repo should show only the user's account.

<!--
Template for each problem:

## Problem N: Title

**Prompt:**

> (exact prompt)

**Follow-up prompt:**

> (exact follow-up prompt)

*What was missing:* (one sentence)
-->
