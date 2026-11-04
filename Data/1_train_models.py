"""
Data/1_train_models.py
======================
Stage 1: train the 6-D venture-risk DNN R(p) and the 8-D telemetry autoencoder B(u)
(PyTorch), save weights and scalers, and compute the ModelHash committed on-chain.

Revision notes
- ModelHash now covers the tensor bytes (not the torch zip container), both scalers,
  the feature schema and the architecture. Previously only two .pt files were hashed (S2).
- All paths are resolved relative to this file, so the script works from any cwd.
- Explicit error if validation loss never improved (no None crash).
- Training order and RNG consumption are unchanged, so trained weights are unchanged.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
MODELS_DIR.mkdir(exist_ok=True)

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

FEATURES_RISK = ["burn_rate", "requested_amount", "milestone_count",
                 "team_experience", "prev_funding", "tam"]
FEATURES_ANOMALY = ["transaction_count", "balance_native", "total_gas_used", "latency_ms",
                    "tx_entropy", "packet_drop_ratio", "vote_clustering", "uptime_ratio"]


class VentureRiskDNN(nn.Module):
    """h1 = ReLU(W1 X + b1) in R^32; h2 = ReLU(W2 Dropout(h1) + b2) in R^16; R = Sigmoid(W3 h2 + b3)."""

    def __init__(self, input_dim=6, dropout_rate=0.2):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 32)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(p=dropout_rate)
        self.fc2 = nn.Linear(32, 16)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        h1 = self.relu1(self.fc1(x))
        h2 = self.relu2(self.fc2(self.dropout(h1)))
        return self.sigmoid(self.fc3(h2))


class AnomalyAutoencoder(nn.Module):
    """Encoder 8 -> 16 -> 4, decoder 4 -> 16 -> 8."""

    def __init__(self, input_dim=8):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_dim, 16), nn.ReLU(), nn.Linear(16, 4), nn.ReLU())
        self.decoder = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, input_dim))

    def forward(self, x):
        return self.decoder(self.encoder(x))


def require_file(name):
    path = HERE / name
    if not path.exists():
        print(f"[-] ERROR: {name} not found next to this script", file=sys.stderr)
        sys.exit(1)
    return path


# ------------------------------------------------------------------------------
# 1. VENTURE RISK DNN R(p)
# ------------------------------------------------------------------------------
print("[STEP 1.1] Loading financial_dataset.csv ...", flush=True)
df_fin = pd.read_csv(require_file("financial_dataset.csv"))
X_risk = df_fin[FEATURES_RISK].values
y_risk = df_fin["is_successful"].values.astype(np.float32).reshape(-1, 1)

X_r_train, X_r_temp, y_r_train, y_r_temp = train_test_split(
    X_risk, y_risk, test_size=0.30, random_state=SEED, stratify=y_risk)
X_r_val, X_r_test, y_r_val, y_r_test = train_test_split(
    X_r_temp, y_r_temp, test_size=0.50, random_state=SEED, stratify=y_r_temp)

scaler_risk = StandardScaler()
X_r_train_s = scaler_risk.fit_transform(X_r_train)
X_r_val_s = scaler_risk.transform(X_r_val)

train_loader_risk = DataLoader(
    TensorDataset(torch.tensor(X_r_train_s, dtype=torch.float32),
                  torch.tensor(y_r_train, dtype=torch.float32)),
    batch_size=256, shuffle=True)
val_loader_risk = DataLoader(
    TensorDataset(torch.tensor(X_r_val_s, dtype=torch.float32),
                  torch.tensor(y_r_val, dtype=torch.float32)),
    batch_size=512, shuffle=False)

risk_model = VentureRiskDNN(input_dim=6, dropout_rate=0.2).to(device)
criterion_bce = nn.BCELoss()
optimizer_risk = optim.Adam(risk_model.parameters(), lr=1e-3, weight_decay=1e-5)

best_val_loss = float("inf")
best_risk_state = None   # deep copies only (S1)

for epoch in range(1, 41):
    risk_model.train()
    running = 0.0
    for bx, by in train_loader_risk:
        bx, by = bx.to(device), by.to(device)
        optimizer_risk.zero_grad()
        loss = criterion_bce(risk_model(bx), by)
        loss.backward()
        optimizer_risk.step()
        running += loss.item() * len(bx)
    train_loss = running / len(X_r_train)

    risk_model.eval()
    val_sum = 0.0
    with torch.no_grad():
        for vx, vy in val_loader_risk:
            vx, vy = vx.to(device), vy.to(device)
            val_sum += criterion_bce(risk_model(vx), vy).item() * len(vx)
    val_loss = val_sum / len(X_r_val)

    if val_loss < best_val_loss:
        best_val_loss = val_loss
        best_risk_state = copy.deepcopy(risk_model.state_dict())

    if epoch % 10 == 0 or epoch == 1:
        print(f"    Epoch [{epoch:02d}/40] train BCE {train_loss:.5f} | val BCE {val_loss:.5f}", flush=True)

if best_risk_state is None:
    sys.exit("[-] ERROR: validation loss never improved; check the risk dataset")
risk_model.load_state_dict(best_risk_state)
torch.save(risk_model.state_dict(), MODELS_DIR / "venture_risk_dnn.pt")
print("[+] Venture Risk DNN saved", flush=True)

# ------------------------------------------------------------------------------
# 2. 8-D TELEMETRY AUTOENCODER B(u), trained on honest traces only
# ------------------------------------------------------------------------------
print("[STEP 1.2] Loading user_behavior_dataset.csv ...", flush=True)
df_user = pd.read_csv(require_file("user_behavior_dataset.csv"))
X_user = df_user[FEATURES_ANOMALY].values
y_user = df_user["is_bot"].values.astype(int)

X_u_train, X_u_temp, y_u_train, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=SEED, stratify=y_user)
X_u_val, X_u_test, y_u_val, y_u_test = train_test_split(
    X_u_temp, y_u_temp, test_size=0.50, random_state=SEED, stratify=y_u_temp)

scaler_user = StandardScaler()
X_u_train_s = scaler_user.fit_transform(X_u_train)
X_u_val_s = scaler_user.transform(X_u_val)

honest_train = X_u_train_s[y_u_train == 0]
honest_val = X_u_val_s[y_u_val == 0]

train_loader_auto = DataLoader(TensorDataset(torch.tensor(honest_train, dtype=torch.float32)),
                               batch_size=512, shuffle=True)
val_loader_auto = DataLoader(TensorDataset(torch.tensor(honest_val, dtype=torch.float32)),
                             batch_size=512, shuffle=False)

autoencoder = AnomalyAutoencoder(input_dim=8).to(device)
criterion_mse = nn.MSELoss()
optimizer_auto = optim.Adam(autoencoder.parameters(), lr=1e-3, weight_decay=1e-6)

best_auto_val = float("inf")
best_auto_state = None

for epoch in range(1, 31):
    autoencoder.train()
    running = 0.0
    for (bx,) in train_loader_auto:
        bx = bx.to(device)
        optimizer_auto.zero_grad()
        loss = criterion_mse(autoencoder(bx), bx)
        loss.backward()
        optimizer_auto.step()
        running += loss.item() * len(bx)
    train_loss = running / len(honest_train)

    autoencoder.eval()
    val_sum = 0.0
    with torch.no_grad():
        for (vx,) in val_loader_auto:
            vx = vx.to(device)
            val_sum += criterion_mse(autoencoder(vx), vx).item() * len(vx)
    val_loss = val_sum / len(honest_val)

    if val_loss < best_auto_val:
        best_auto_val = val_loss
        best_auto_state = copy.deepcopy(autoencoder.state_dict())

    if epoch % 10 == 0 or epoch == 1:
        print(f"    Epoch [{epoch:02d}/30] train MSE {train_loss:.6f} | val MSE {val_loss:.6f}", flush=True)

if best_auto_state is None:
    sys.exit("[-] ERROR: autoencoder validation loss never improved")
autoencoder.load_state_dict(best_auto_state)
torch.save(autoencoder.state_dict(), MODELS_DIR / "telemetry_autoencoder.pt")
print("[+] Anomaly Autoencoder saved", flush=True)

# ------------------------------------------------------------------------------
# 3. SCALERS AND MODELHASH (S2: everything that affects the output is covered)
# ------------------------------------------------------------------------------
joblib.dump({
    "scaler_risk": scaler_risk,
    "scaler_user": scaler_user,
    "feature_cols_risk": FEATURES_RISK,
    "feature_cols_anomaly": FEATURES_ANOMALY,
}, MODELS_DIR / "scalers.joblib")


def digest_state(hasher, state):
    for key in sorted(state):
        hasher.update(key.encode("utf-8"))
        hasher.update(state[key].detach().cpu().contiguous().numpy().tobytes())


def digest_scaler(hasher, scaler):
    hasher.update(np.asarray(scaler.mean_, dtype=np.float64).tobytes())
    hasher.update(np.asarray(scaler.scale_, dtype=np.float64).tobytes())


hasher = hashlib.sha256()
digest_state(hasher, risk_model.state_dict())
digest_state(hasher, autoencoder.state_dict())
digest_scaler(hasher, scaler_risk)
digest_scaler(hasher, scaler_user)
hasher.update(json.dumps({
    "features_risk": FEATURES_RISK,
    "features_anomaly": FEATURES_ANOMALY,
    "architecture": ["risk 6-32-16-1 dropout0.2", "autoencoder 8-16-4-16-8"],
    "seed": SEED,
}, sort_keys=True).encode("utf-8"))

model_hash_hex = "0x" + hasher.hexdigest()
with open(MODELS_DIR / "model_hash.json", "w", encoding="utf-8") as f:
    json.dump({"model_hash": model_hash_hex, "algorithm": "sha256",
               "covers": ["risk weights", "autoencoder weights", "scalers",
                          "feature schema", "architecture"]}, f, indent=4)

print(f"[+] ModelHash: {model_hash_hex}", flush=True)
print("[STAGE 1 COMPLETE]", flush=True)
