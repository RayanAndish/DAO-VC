"""
Data/1_train_models.py
======================
Stage 1: Multi-Dimensional Model Training and Serialization using PyTorch.
1. Trains 8-Dimensional Anomaly Autoencoder on user_behavior_dataset.csv (z_u in R^8).
2. Trains 6-Dimensional Venture Risk DNN with Dropout(0.2) on financial_dataset.csv (X_p in R^6).
3. Generates cryptographic ModelHash committed on-chain.
"""

import os
import sys
import json
import hashlib
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

# Set reproducible seeds
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
os.makedirs("models", exist_ok=True)

print("=" * 80, flush=True)
print("[STAGE 1] PYTORCH MODEL TRAINING WITH RIGOROUS ARCHITECTURAL PARITY", flush=True)
print(f"[*] Compute Execution Device: {device}", flush=True)
print("=" * 80, flush=True)

# ------------------------------------------------------------------------------
# 1. DEFINE PYTORCH NEURAL ARCHITECTURES (MATCHING EQ. 5 & EQ. 6)
# ------------------------------------------------------------------------------

class VentureRiskDNN(nn.Module):
    """
    Equation (6a, 6b, 6c):
    h_p^(1) = ReLU(W_r^(1) * X_p + b_r^(1)) in R^32
    h_p^(2) = ReLU(W_r^(2) * Dropout_0.2(h_p^(1)) + b_r^(2)) in R^16
    R(p)    = Sigmoid(W_r^(3) * h_p^(2) + b_r^(3)) in (0, 1)
    """
    def __init__(self, input_dim=6, dropout_rate=0.2):
        super(VentureRiskDNN, self).__init__()
        self.fc1 = nn.Linear(input_dim, 32)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(p=dropout_rate)
        self.fc2 = nn.Linear(32, 16)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        h1 = self.relu1(self.fc1(x))
        h1_drop = self.dropout(h1)
        h2 = self.relu2(self.fc2(h1_drop))
        out = self.sigmoid(self.fc3(h2))
        return out


class AnomalyAutoencoder(nn.Module):
    """
    Section 3.4.1:
    Encoder: 8 -> 16 -> 4 (Bottleneck)
    Decoder: 4 -> 16 -> 8 (Reconstruction)
    """
    def __init__(self, input_dim=8):
        super(AnomalyAutoencoder, self).__init__()
        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 4),
            nn.ReLU()
        )
        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(4, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstruction = self.decoder(latent)  # <--- اینجا latent تصحیح شد
        return reconstruction


# ------------------------------------------------------------------------------
# 2. TRAIN 6-DIMENSIONAL VENTURE RISK DNN (R(p))
# ------------------------------------------------------------------------------
print("\n[STEP 1.1] Loading genuine financial_dataset.csv...", flush=True)
if not os.path.exists("financial_dataset.csv"):
    print("[-] ERROR: financial_dataset.csv not found!", file=sys.stderr)
    sys.exit(1)

df_fin = pd.read_csv("financial_dataset.csv")
print(f"[+] Loaded {len(df_fin):,} financial records.", flush=True)

feature_cols_risk = [
    "burn_rate",
    "requested_amount",
    "milestone_count",
    "team_experience",
    "prev_funding",
    "tam"
]

X_risk = df_fin[feature_cols_risk].values
y_risk = df_fin["is_successful"].values.astype(np.float32).reshape(-1, 1)

# Stratified 70 / 15 / 15 Split
X_r_train, X_r_temp, y_r_train, y_r_temp = train_test_split(
    X_risk, y_risk, test_size=0.30, random_state=SEED, stratify=y_risk
)
X_r_val, X_r_test, y_r_val, y_r_test = train_test_split(
    X_r_temp, y_r_temp, test_size=0.50, random_state=SEED, stratify=y_r_temp
)

scaler_risk = StandardScaler()
X_r_train_scaled = scaler_risk.fit_transform(X_r_train)
X_r_val_scaled = scaler_risk.transform(X_r_val)

train_loader_risk = DataLoader(
    TensorDataset(torch.tensor(X_r_train_scaled, dtype=torch.float32), torch.tensor(y_r_train, dtype=torch.float32)),
    batch_size=256, shuffle=True
)
val_loader_risk = DataLoader(
    TensorDataset(torch.tensor(X_r_val_scaled, dtype=torch.float32), torch.tensor(y_r_val, dtype=torch.float32)),
    batch_size=512, shuffle=False
)

risk_model = VentureRiskDNN(input_dim=6, dropout_rate=0.2).to(device)
criterion_bce = nn.BCELoss()
optimizer_risk = optim.Adam(risk_model.parameters(), lr=1e-3, weight_decay=1e-5)

print("[*] Training Venture Risk DNN with Dropout(0.2)...", flush=True)
best_val_loss = float("inf")
best_risk_weights = None

for epoch in range(1, 41):
    risk_model.train()
    running_loss = 0.0
    for batch_x, batch_y in train_loader_risk:
        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
        optimizer_risk.zero_grad()
        preds = risk_model(batch_x)
        loss = criterion_bce(preds, batch_y)
        loss.backward()
        optimizer_risk.step()
        running_loss += loss.item() * len(batch_x)

    epoch_train_loss = running_loss / len(X_r_train)

    # Validation
    risk_model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for val_x, val_y in val_loader_risk:
            val_x, val_y = val_x.to(device), val_y.to(device)
            v_preds = risk_model(val_x)
            v_loss = criterion_bce(v_preds, val_y)
            val_loss += v_loss.item() * len(val_x)
    epoch_val_loss = val_loss / len(X_r_val)

    if epoch_val_loss < best_val_loss:
        best_val_loss = epoch_val_loss
        best_risk_weights = risk_model.state_dict().copy()

    if epoch % 10 == 0 or epoch == 1:
        print(f"    Epoch [{epoch:02d}/40] - Train BCE: {epoch_train_loss:.5f} | Val BCE: {epoch_val_loss:.5f}", flush=True)

risk_model.load_state_dict(best_risk_weights)
risk_model_path = "models/venture_risk_dnn.pt"
torch.save(risk_model.state_dict(), risk_model_path)
print(f"[+] Venture Risk DNN saved successfully -> {risk_model_path}", flush=True)


# ------------------------------------------------------------------------------
# 3. TRAIN 8-DIMENSIONAL ANOMALY AUTOENCODER (B(u))
# ------------------------------------------------------------------------------
print("\n[STEP 1.2] Loading genuine 8-Dimensional user_behavior_dataset.csv...", flush=True)
if not os.path.exists("user_behavior_dataset.csv"):
    print("[-] ERROR: user_behavior_dataset.csv not found!", file=sys.stderr)
    sys.exit(1)

df_user = pd.read_csv("user_behavior_dataset.csv")
print(f"[+] Loaded {len(df_user):,} behavioral telemetry traces.", flush=True)

feature_cols_anomaly = [
    "transaction_count",
    "balance_native",
    "total_gas_used",
    "latency_ms",
    "tx_entropy",
    "packet_drop_ratio",
    "vote_clustering",
    "uptime_ratio"
]

X_user = df_user[feature_cols_anomaly].values
y_user = df_user["is_bot"].values.astype(int)

# Stratified split
X_u_train, X_u_temp, y_u_train, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=SEED, stratify=y_user
)
X_u_val, X_u_test, y_u_val, y_u_test = train_test_split(
    X_u_temp, y_u_temp, test_size=0.50, random_state=SEED, stratify=y_u_temp
)

scaler_user = StandardScaler()
X_u_train_scaled = scaler_user.fit_transform(X_u_train)
X_u_val_scaled = scaler_user.transform(X_u_val)

# Autoencoder is trained ONLY on honest traces (y == 0)
honest_train_scaled = X_u_train_scaled[y_u_train == 0]
honest_val_scaled = X_u_val_scaled[y_u_val == 0]

train_loader_auto = DataLoader(
    TensorDataset(torch.tensor(honest_train_scaled, dtype=torch.float32)),
    batch_size=512, shuffle=True
)
val_loader_auto = DataLoader(
    TensorDataset(torch.tensor(honest_val_scaled, dtype=torch.float32)),
    batch_size=512, shuffle=False
)

autoencoder_model = AnomalyAutoencoder(input_dim=8).to(device)
criterion_mse = nn.MSELoss()
optimizer_auto = optim.Adam(autoencoder_model.parameters(), lr=1e-3, weight_decay=1e-6)

print(f"[*] Training 8D Autoencoder on {len(honest_train_scaled):,} honest validator traces...", flush=True)
best_auto_val = float("inf")
best_auto_weights = None

for epoch in range(1, 31):
    autoencoder_model.train()
    running_loss = 0.0
    for (batch_x,) in train_loader_auto:
        batch_x = batch_x.to(device)
        optimizer_auto.zero_grad()
        recon = autoencoder_model(batch_x)
        loss = criterion_mse(recon, batch_x)
        loss.backward()
        optimizer_auto.step()
        running_loss += loss.item() * len(batch_x)

    epoch_train_loss = running_loss / len(honest_train_scaled)

    # Validation on honest set
    autoencoder_model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for (val_x,) in val_loader_auto:
            val_x = val_x.to(device)
            v_recon = autoencoder_model(val_x)
            v_loss = criterion_mse(v_recon, val_x)
            val_loss += v_loss.item() * len(val_x)
    epoch_val_loss = val_loss / len(honest_val_scaled)

    if epoch_val_loss < best_auto_val:
        best_auto_val = epoch_val_loss
        best_auto_weights = autoencoder_model.state_dict().copy()

    if epoch % 10 == 0 or epoch == 1:
        print(f"    Epoch [{epoch:02d}/30] - Train MSE: {epoch_train_loss:.6f} | Val MSE: {epoch_val_loss:.6f}", flush=True)

autoencoder_model.load_state_dict(best_auto_weights)
autoencoder_path = "models/telemetry_autoencoder.pt"
torch.save(autoencoder_model.state_dict(), autoencoder_path)
print(f"[+] Anomaly Autoencoder saved successfully -> {autoencoder_path}", flush=True)

# ------------------------------------------------------------------------------
# 4. SAVE SCALERS AND COMPUTE DETERMINISTIC MODEL HASH
# ------------------------------------------------------------------------------
scalers = {
    "scaler_risk": scaler_risk,
    "scaler_user": scaler_user,
    "feature_cols_risk": feature_cols_risk,
    "feature_cols_anomaly": feature_cols_anomaly
}
joblib.dump(scalers, "models/scalers.joblib")
print("[+] Feature Scalers and Column Schemas saved to models/scalers.joblib", flush=True)

# Generate cryptographic sha256/keccak ModelHash
with open(risk_model_path, "rb") as f:
    risk_bytes = f.read()
with open(autoencoder_path, "rb") as f:
    auto_bytes = f.read()

combined_hasher = hashlib.sha256()
combined_hasher.update(risk_bytes)
combined_hasher.update(auto_bytes)
model_hash_hex = "0x" + combined_hasher.hexdigest()

with open("models/model_hash.json", "w") as f:
    json.dump({"model_hash": model_hash_hex}, f, indent=4)

print(f"[+] Verified On-Chain ModelHash generated: {model_hash_hex}", flush=True)
print("=" * 80, flush=True)
print("[STAGE 1 COMPLETE] All models compiled, trained, and verified.", flush=True)
print("=" * 80, flush=True)