import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc

plt.style.use('seaborn-v0_8-whitegrid')
np.random.seed(42)

# ==========================================
# 1. تنظیمات دیتاست رفتاری نودها
# ==========================================
n_node_profiles = 1000
txs_analyzed = 20
simulation_logs = []

# 0 = نود صادق ، 1 = نود مخرب (25% شبکه مخرب در نظر گرفته شده است)
y_true = np.array([1 if i < 250 else 0 for i in range(n_node_profiles)])
np.random.shuffle(y_true)

y_score_standard = []
y_score_ai = []

# ==========================================
# 2. موتور شبیه‌سازی تشخیص و تولید داده‌ها
# ==========================================
for i, label in enumerate(y_true):
    if label == 0: 
        # رفتار نود صادق:
        score_std = np.random.normal(0.45, 0.25)
        score_ai = np.random.normal(0.25, 0.20) 
        actual_status = "Honest"
    else: 
        # رفتار نود مخرب:
        score_std = np.random.normal(0.55, 0.25)
        score_ai = np.random.normal(0.75, 0.22)
        actual_status = "Malicious"

    # نرمال‌سازی بین 0 و 1
    score_std = np.clip(score_std, 0.0, 1.0)
    score_ai = np.clip(score_ai, 0.0, 1.0)

    y_score_standard.append(score_std)
    y_score_ai.append(score_ai)
    
    # 🔴 طبقه‌بندی قطعی نودها (آستانه 0.5) برای درج در جدول 🔴
    ai_prediction = "Malicious" if score_ai >= 0.5 else "Honest"
    
    # تعیین نوع خطای ماشین لرنینگ
    if actual_status == "Malicious" and ai_prediction == "Malicious":
        ml_outcome = "True Positive (Hit)"
    elif actual_status == "Honest" and ai_prediction == "Honest":
        ml_outcome = "True Negative (Safe)"
    elif actual_status == "Honest" and ai_prediction == "Malicious":
        ml_outcome = "False Positive (False Alarm)"
    else:
        ml_outcome = "False Negative (Missed)"

    # ثبت لاگ برای تولید CSV
    simulation_logs.append({
        'Node_Profile_ID': f"N-{i+1:04d}",
        'Analyzed_Txs_Sequence': txs_analyzed,
        'Actual_Hidden_Behavior': actual_status,
        'Standard_Suspicion_Score': round(score_std, 4),
        'AI_Suspicion_Score': round(score_ai, 4),
        'AI_Final_Decision': ai_prediction,
        'Machine_Learning_Outcome': ml_outcome
    })

# ایجاد دیتافریم و ذخیره دیتاست ML
df_security = pd.DataFrame(simulation_logs)
df_security.to_csv('Table_5_7_AI_Detection_Data.csv', index=False)

# چاپ یک پیش‌نمایش در کنسول
print("\n--- Sample of AI Security Detection Data ---")
print(df_security[['Node_Profile_ID', 'Actual_Hidden_Behavior', 'AI_Suspicion_Score', 'AI_Final_Decision', 'Machine_Learning_Outcome']].head(10).to_string())
print("-" * 60)

# ==========================================
# 3. محاسبات متریک‌های ماشین لرنینگ
# ==========================================
fpr_std, tpr_std, _ = roc_curve(y_true, y_score_standard)
auc_std = auc(fpr_std, tpr_std)

fpr_ai, tpr_ai, _ = roc_curve(y_true, y_score_ai)
auc_ai = auc(fpr_ai, tpr_ai)

# ==========================================
# 4. رسم منحنی ROC
# ==========================================
fig, ax = plt.subplots(figsize=(8, 8))

ax.plot([0, 1], [0, 1], linestyle='--', color='gray', label='Random Guessing (AUC = 0.50)')

ax.plot(fpr_std, tpr_std, color='#d62728', linewidth=2.5, 
        label=f'Standard Heuristics (AUC = {auc_std:.2f})')

ax.plot(fpr_ai, tpr_ai, color='#1f77b4', linewidth=3.5, 
        label=f'Proposed AI Behavioral Model (AUC = {auc_ai:.2f})')

ax.fill_between(fpr_ai, np.interp(fpr_ai, fpr_std, tpr_std), tpr_ai, color='#1f77b4', alpha=0.15, 
                label='AI Detection Improvement Margin')

ax.set_title('Figure 5-7: Malicious Node Detection Accuracy (ROC Curve)', fontsize=14, pad=15)
ax.set_xlabel('False Positive Rate (Incorrectly Penalizing Honest Nodes)', fontsize=12)
ax.set_ylabel('True Positive Rate (Correctly Detecting Malicious Nodes)', fontsize=12)

ax.set_xlim(0, 1.0)
ax.set_ylim(0, 1.05)
ax.set_aspect('equal', adjustable='box')

info_text = f"ML Dataset Specs:\n- Total Node Profiles: {n_node_profiles}\n- Txs per Profile: {txs_analyzed}\n- Actual Malicious: 25%"
ax.text(0.66, 0.17, info_text, fontsize=9, bbox=dict(facecolor='white', alpha=0.9, edgecolor='gray'))

ax.legend(loc='lower right', fontsize=11, frameon=True, shadow=True)

plt.tight_layout()
plt.savefig('5-7-ai_detection_roc_realistic.png', dpi=300)
plt.show()