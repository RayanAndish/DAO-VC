"""
1_train_models.py
=================
Stage 1: Model Training and Serialization.
Trains Venture Risk DNN and Anomaly Detection Autoencoder on genuine datasets,
saves serialized model artifacts to disk, and computes cryptographic ModelHash.
"""

import hashlib
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import StandardScaler

np.random.seed(42)
os.makedirs("models", exist_ok=True)

print("=" * 80)
print("STAGE 1: TRAINING AND SERIALIZING OFF-CHAIN AI MODELS")
print("=" * 80)

# ------------------------------------------------------------------------------
# 1. TRAIN VENTURE RISK DNN (R(p))
# ------------------------------------------------------------------------------
print("\n[*] Loading financial_dataset.csv (500,000 records)...")
df_fin = pd.read_csv("financial_dataset.csv")

feature_cols_risk = [
    "burn_rate",
    "requested_amount",
    "milestone_count",
    "team_experience",
    "prev_funding",
    "tam",
]
X_risk = df_fin[feature_cols_risk].copy()
y_risk = df_fin["is_successful"].values

# 70% Train, 30% Temp (Val + Test)
X_r_train, X_r_temp, y_r_train, y_r_temp = train_test_split(
    X_risk, y_risk, test_size=0.30, random_state=42, stratify=y_risk
)

scaler_risk = StandardScaler()
X_r_train_scaled = scaler_risk.fit_transform(X_r_train)

# DNN Architecture: Input(6) -> Dense(32) -> Dense(16) -> Output(1)
risk_dnn = MLPClassifier(
    hidden_layer_sizes=(32, 16),
    activation="relu",
    solver="adam",
    learning_rate_init=1e-3,
    max_iter=100,
    random_state=42,
    batch_size=256,
    early_stopping=True,
    n_iter_no_change=10,
)

print(
    f"[*] Training Venture Risk DNN on {len(X_r_train):,} training records..."
)
risk_dnn.fit(X_r_train_scaled, y_r_train)

# Save Risk Model & Scaler
risk_model_path = "models/venture_risk_dnn.joblib"
joblib.dump(risk_dnn, risk_model_path)
print(f"[+] Venture Risk DNN saved to: {risk_model_path}")

# ------------------------------------------------------------------------------
# 2. TRAIN ANOMALY AUTOENCODER (B(u))
# ------------------------------------------------------------------------------
print("\n[*] Loading user_behavior_dataset.csv (600,000 records)...")
df_user = pd.read_csv("user_behavior_dataset.csv")

feature_cols_anomaly = ["transaction_count", "balance_native", "total_gas_used"]
X_user = df_user[feature_cols_anomaly].copy()
y_user = df_user["is_bot"].values

X_u_train, X_u_temp, y_u_train, y_u_temp = train_test_split(
    X_user, y_user, test_size=0.30, random_state=42, stratify=y_user
)

scaler_user = StandardScaler()
X_u_train_scaled = scaler_user.fit_transform(X_u_train)

# Unsupervised Autoencoder: Trained strictly on honest nodes (is_bot == 0)
honest_train_scaled = X_u_train_scaled[y_u_train == 0]

autoencoder = MLPRegressor(
    hidden_layer_sizes=(16, 4, 16),
    activation="relu",
    solver="adam",
    learning_rate_init=1e-3,
    max_iter=50,
    random_state=42,
    batch_size=512,
    early_stopping=True,
    n_iter_no_change=5,
)

print(
    f"[*] Training Autoencoder on {len(honest_train_scaled):,} honest telemetry"
    " traces..."
)
autoencoder.fit(honest_train_scaled, honest_train_scaled)

autoencoder_path = "models/telemetry_autoencoder.joblib"
joblib.dump(autoencoder, autoencoder_path)
print(f"[+] Anomaly Autoencoder saved to: {autoencoder_path}")

# Save Scalers for consistent downstream evaluation
scalers = {
    "scaler_risk": scaler_risk,
    "scaler_user": scaler_user,
    "feature_cols_risk": feature_cols_risk,
    "feature_cols_anomaly": feature_cols_anomaly,
}
joblib.dump(scalers, "models/scalers.joblib")
print("[+] Feature scalers saved to: models/scalers.joblib")

# ------------------------------------------------------------------------------
# 3. COMPUTE ON-CHAIN CRYPTOGRAPHIC MODEL HASH (Eq. 7 & Section 6.3)
# ------------------------------------------------------------------------------
with open(risk_model_path, "rb") as f:
    model_bytes = f.read()
model_hash = hashlib.sha256(model_bytes).hexdigest()

print("\n" + "=" * 80)
print(f">>> CRYPTOGRAPHIC MODEL HASH (SHA-256 / KECCAK PROVENANCE):")
print(f"    Hash(Theta) = 0x{model_hash}")
print(
    "    (This digest is committed on-chain via Eq. 7 to guarantee neural"
    " integrity)"
)
print("=" * 80)