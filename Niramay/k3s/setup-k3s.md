# K3s Setup Guide — Niramay Self-Healing Layer

## Prerequisites

- **Windows 10/11** with **WSL2** enabled
- **Docker Desktop** (or Docker inside WSL2)
- Project cloned locally

---

## Step 1 — Install WSL2

Open **PowerShell as Administrator**:

```powershell
wsl --install
wsl --set-default-version 2
```

Install **Ubuntu** from the Microsoft Store, then open the Ubuntu terminal.

---

## Step 2 — Install K3s

Inside the **WSL2 Ubuntu terminal**:

```bash
# Install K3s (single command — includes kubectl)
curl -sfL https://get.k3s.io | sh -

# Wait for K3s to start (~30 seconds)
sudo k3s kubectl get nodes
# Expected output:
# NAME    STATUS   ROLES                  AGE   VERSION
# ...     Ready    control-plane,master   30s   v1.x.x+k3s1
```

---

## Step 3 — Configure kubectl

```bash
# Copy K3s kubeconfig to standard location
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config

# Verify kubectl works without sudo
kubectl get nodes
```

---

## Step 4 — Build and Import Images

K3s uses **containerd** (not Docker's image store), so images must be
explicitly imported after building:

```bash
# Build Niramay backend image
cd /path/to/healing-layer/Niramay
docker build -t niramay-backend:latest ./backend

# Build Crave backend image
cd /path/to/Crave
docker build -t crave-backend:latest .

# Import into K3s containerd
docker save niramay-backend:latest | sudo k3s ctr images import -
docker save crave-backend:latest   | sudo k3s ctr images import -

# Verify images are available
sudo k3s ctr images list | grep -E 'niramay|crave'
```

> **Important:** Every time you rebuild an image, you must re-import it
> into K3s with the `docker save | k3s ctr images import` command.

---

## Step 5 — Deploy to K3s

```bash
cd /path/to/healing-layer/Niramay

# 1. Create RBAC (ServiceAccount + ClusterRole)
kubectl apply -f k3s/niramay-rbac.yaml

# 2. Deploy Crave backend (the healing target)
kubectl apply -f k3s/crave-deployment.yaml

# 3. Deploy Niramay backend (the healer)
kubectl apply -f k3s/niramay-deployment.yaml

# 4. Wait for pods to be ready
kubectl rollout status deployment/crave-backend
kubectl rollout status deployment/niramay-backend
```

---

## Step 6 — Verify

```bash
# Check all pods are Running
kubectl get pods -o wide

# Check Niramay is healthy
NIRAMAY_URL=$(kubectl get svc niramay-backend -o jsonpath='{.spec.clusterIP}')
curl http://$NIRAMAY_URL:8000/health

# Check Crave is healthy
CRAVE_URL=$(kubectl get svc crave-backend -o jsonpath='{.spec.clusterIP}')
curl http://$CRAVE_URL:8000/health
```

---

## Step 7 — Access from Outside the Cluster

Niramay uses a **NodePort** service. To get the external URL:

```bash
# Get the NodePort assigned to niramay-backend
kubectl get svc niramay-backend
# Look for the PORT(S) column: 8000:<NodePort>/TCP

# Access from Windows browser or tests:
# http://localhost:<NodePort>
```

---

## Useful Commands

```bash
# View Niramay logs
kubectl logs deployment/niramay-backend -f

# View Crave logs
kubectl logs deployment/crave-backend -f

# Restart Crave manually (same as what k3s_restart.py does)
kubectl rollout restart deployment/crave-backend

# Scale Crave manually (same as what k3s_scale_up.py does)
kubectl scale deployment/crave-backend --replicas=3

# Check healing actions in Niramay
curl http://localhost:<NodePort>/api/v1/observation/healing-actions

# Uninstall K3s (if needed)
/usr/local/bin/k3s-uninstall.sh
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `kubectl: command not found` | Run `export PATH=$PATH:/usr/local/bin` or use `sudo k3s kubectl` |
| Pod stuck in `ImagePullBackOff` | You forgot `imagePullPolicy: Never` or didn't import the image |
| Pod stuck in `CrashLoopBackOff` | Check logs: `kubectl logs <pod-name>` |
| `RBAC: access denied` | Re-apply RBAC: `kubectl apply -f k3s/niramay-rbac.yaml` |
| K3s not starting in WSL2 | Try: `sudo systemctl start k3s` |
