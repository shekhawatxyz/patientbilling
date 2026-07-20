# Run from zero

Prerequisites: Docker Engine/Desktop with Compose v2, Node.js 18+, npm, and curl.

```bash
git clone https://github.com/shekhawatxyz/patientbilling.git
cd patientbilling
bash deploy/scripts/start_demo.sh
```

The startup command creates its local `.env`, builds the frontend, starts all five
services, initializes Zango, seeds the demo, and selects the zero-cost
`local_fake` AI provider.

- App: <http://patientbilling.localhost:8000/app/>
- Platform: <http://localhost:8000/platform/>
- Manager: `manager@billing.local` / `Billing@123`
- Staff: `staff@billing.local` / `Billing@123`

If `patientbilling.localhost` does not resolve to loopback, add this exact hosts
entry and rerun the startup command:

```text
127.0.0.1 patientbilling.localhost
```

To remove the disposable database and containers before another clean run:

```bash
docker compose -f deploy/docker_compose.yml down -v
```

Then delete the clone, clone again, and run only `bash deploy/scripts/start_demo.sh`.
