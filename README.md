# pg-ha-fullstack

PostgreSQL 18 high-availability cluster with a Flask REST API and nginx reverse proxy,
running in Docker Compose inside a Fedora 42 VM provisioned by Vagrant.

Patroni handles leader election and automatic failover. etcd provides the distributed
consensus backend. The standby runs in synchronous mode — a transaction is not
acknowledged until it is written on both nodes, so no data is lost if the leader dies.
The Flask app connects via a multi-host connection string with `target_session_attrs=read-write`,
so it always finds the writable node regardless of which one Patroni promoted.

---

## Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │       Fedora 42 VM (Vagrant + libvirt)       │
                       │                                              │
                       │  ┌──────────────────────────────────────┐    │
                       │  │       Docker network: pgnet          │    │
                       │  │                                      │    │
                       │  │  etcd1 ─┐                            │    │
                       │  │  etcd2 ─┼── Raft consensus           │    │
                       │  │  etcd3 ─┘       │                    │    │
                       │  │                 │ DCS                │    │
                       │  │         ┌───────┴────────┐           │    │
                       │  │         │    pg-node1    │           │    │
                       │  │         │  Patroni+PG18  │           │    │
                       │  │         │  (role varies) │           │    │
                       │  │         └───────┬────────┘           │    │
                       │  │                 │                    │    │
                       │  │      synchronous replication         │    │
                       │  │                 │                    │    │
                       │  │         ┌───────┴────────┐           │    │
                       │  │         │    pg-node2    │           │    │
                       │  │         │  Patroni+PG18  │           │    │
                       │  │         │  (role varies) │           │    │
                       │  │         └───────┬────────┘           │    │
                       │  │                 │                    │    │
                       │  │         ┌───────┴────────┐           │    │
                       │  │         │   flask-app    │           │    │
                       │  │         │  Flask REST API│           │    │
                       │  │         └───────┬────────┘           │    │
                       │  │                 │                    │    │
                       │  │         ┌───────┴────────┐           │    │
                       │  │         │     nginx      │           │    │
                       │  │         │  reverse proxy │           │    │
                       │  │         └───────┬────────┘           │    │
                       │  │                 │ port 80            │    │
                       │  └─────────────────┼────────────────────┘    │
                       │                    │                         │
                       │   curl localhost/api/orders                  │
                       └──────────────────────────────────────────────┘
```

### Components

| Container | Role | Ports |
|-----------|------|-------|
| `etcd1`, `etcd2`, `etcd3` | Raft consensus cluster — Patroni DCS backend | 2379 (client), 2380 (peer) |
| `pg-node1` | PostgreSQL 18 + Patroni — leader or sync standby | 5432, 8008 (REST API) |
| `pg-node2` | PostgreSQL 18 + Patroni — leader or sync standby | 5432, 8008 (REST API) |
| `flask-app` | Flask REST API — data ingestion and query layer | 5000 |
| `nginx` | Reverse proxy — routes HTTP requests to Flask | 80 |

### How failover works

1. Patroni on each PostgreSQL node holds a lease in etcd. The leader renews it every
   `loop_wait` seconds (10 s).
2. If the leader misses enough renewals, etcd expires the key and the cluster enters
   an election.
3. The sync standby is guaranteed to be up to date (synchronous replication), so it
   is promoted immediately without any data loss.
4. The old leader comes back, detects it is no longer the leader, and uses
   `pg_rewind` to fast-forward its WAL to the new leader's timeline. It then
   rejoins as a replica — no manual intervention required.
5. The Flask app uses a multi-host connection string so it automatically finds the
   new leader on the next request. No config change needed.

---

## Stack

| Component | Version | Source |
|-----------|---------|--------|
| PostgreSQL | 18 (PGDG) | `pgdg-fedora-repo` |
| Patroni | 4.x | `pip install patroni[psycopg3,etcd3]` |
| etcd | 3.5 | `dnf install etcd` |
| Flask | 3.x | `pip install flask` |
| psycopg | 3.x | `pip install psycopg[binary]` |
| nginx | latest | Docker Hub |
| Base image (PG) | `fedora:42` | Docker Hub |
| Base image (Flask) | `python:3-slim` | Docker Hub |

---

## Prerequisites

- Vagrant with the `vagrant-libvirt` provider
- libvirt / KVM on the host
- 2 GB RAM and 2 vCPUs available for the VM

---

## Quick start

```bash
git clone git@github.com:rafalwitalski/pg-ha-fullstack.git
cd pg-ha-fullstack
vagrant up
```

Vagrant provisions a Fedora 42 VM, installs Docker CE, builds the images, and starts
all seven containers. First run takes a few minutes while images build and Patroni
initialises the cluster.

SSH into the VM and check cluster state:

```bash
vagrant ssh
docker exec pg-node1 patronictl -c /etc/patroni/patroni.yml list
```

Expected output once the cluster is healthy:

```
+ Cluster: pg-cluster (xxxxxxxxxxxxxxxx) +----+-----------+----+-----------+
| Member   | Host     | Role         | State     | TL | Lag in MB |
+----------+----------+--------------+-----------+----+-----------+
| pg-node1 | pg-node1 | Leader       | running   |  1 |           |
| pg-node2 | pg-node2 | Sync Standby | streaming |  1 |         0 |
+----------+----------+--------------+-----------+----+-----------+
```

Test the API:

```bash
curl localhost/api/orders -d '{"item":"widget","qty":5}' -H "Content-Type: application/json"
# {"item":"widget","qty":5,"status":"created"}

curl localhost/api/orders
# [{"id":1,"item":"widget","qty":5}]

curl localhost/health
# {"db":"postgresql://...","status":"ok"}
```

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/orders` | Create an order. Body: `{"item": "...", "qty": N}` |
| `GET` | `/api/orders` | List all orders |
| `GET` | `/health` | Health check with database connection info |

---

## Testing failover

```bash
# 1. Check which node is leader
docker exec pg-node1 patronictl -c /etc/patroni/patroni.yml list

# 2. Stop the leader (assume it's pg-node2)
docker stop pg-node2

# 3. Watch the standby get promoted (~10 seconds)
docker exec pg-node1 patronictl -c /etc/patroni/patroni.yml list

# 4. Write through the API — the app finds the new leader automatically
curl localhost/api/orders -d '{"item":"gizmo","qty":3}' -H "Content-Type: application/json"

# 5. Verify both rows are present (zero data loss)
curl localhost/api/orders

# 6. Bring the old leader back — it rejoins as a replica
docker start pg-node2
sleep 10
docker exec pg-node1 patronictl -c /etc/patroni/patroni.yml list
```

---

## Project files

```
.
├── Dockerfile              # PostgreSQL 18 + Patroni image (fedora:42)
├── Dockerfile.etcd         # etcd image
├── docker-compose.yml      # all 7 services: etcd, PG, Flask, nginx
├── patroni.yml             # shared Patroni config; per-node identity via env vars
├── docker.sh               # Vagrant provisioner — installs Docker, starts cluster
├── Vagrantfile             # Fedora 42 VM, libvirt provider, rsync shared folder
├── app/
│   ├── Dockerfile          # Flask image (python:3-slim)
│   ├── app.py              # Flask REST API
│   └── requirements.txt    # flask, psycopg[binary]
└── nginx/
    └── nginx.conf           # reverse proxy config
```

---

## Resetting the cluster

```bash
# From inside the VM
cd /vagrant && docker compose down -v && docker compose up -d
```

The `-v` flag removes named volumes, forcing PostgreSQL to reinitialise and Patroni
to bootstrap a fresh cluster on the next start.
