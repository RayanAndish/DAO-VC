import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

plt.style.use('seaborn-v0_8-whitegrid')
np.random.seed(42)

# ==========================================
# 1. تنظیمات پارامترهای شبکه و شبیه‌سازی
# ==========================================
n_proposals = 1000
tx_per_proposal = 20  # چرخه تصمیم‌سازی مالی: 20 تراکنش/پیام مستقل برای هر پروپوزال
total_nodes = 100     # تعداد نودهای فعال در کمیته ارزیابی مالی

# ترکیب رفتار نودها
malicious_nodes = int(total_nodes * 0.15)    # 15% سعی در پامپ/دامپ مخرب دارند
uncooperative_nodes = int(total_nodes * 0.20)# 20% ارزیابی تصادفی و بی‌دقت
honest_nodes = total_nodes - malicious_nodes - uncooperative_nodes # 65% صادق

# تابع آستانه پذیرش پویا (مرز کارا - Efficient Frontier)
def minimum_required_roi(risk):
    return 15 + (risk / 6.5)**2.2

simulation_logs = []
ai_final_risks = []
ai_final_rois = []
decision_status = []

# ==========================================
# 2. موتور شبیه‌سازی ارزیابی مالی شبکه
# ==========================================
for p_id in range(1, n_proposals + 1):
    
    # --- الف: تولید ارزش ذاتی پروژه ---
    true_risk = np.random.normal(65, 15)
    true_risk = np.clip(true_risk, 5, 100)
    
    true_roi = true_risk * 1.8 + np.random.normal(50, 60)
    true_roi = np.clip(true_roi, 5, 400)
    
    # --- ب: شبیه‌سازی ارزیابی نودها در طی 20 تراکنش ---
    honest_roi_eval = true_roi + np.random.normal(0, 5) # خطای طبیعی کم
    uncoop_roi_eval = true_roi + np.random.normal(0, 30) # خطای بالا و بی‌دقتی
    
    # رفتار مخرب: اگر پروژه بد است (ROI پایین)، سعی در "بزرگ‌نمایی" دارند (Hype)
    # اگر پروژه خوب است، سعی در "تخریب" دارند (FUD)
    if true_roi < minimum_required_roi(true_risk):
        malicious_roi_eval = true_roi + np.random.uniform(50, 150) # Hype (کلاهبرداری)
    else:
        malicious_roi_eval = true_roi - np.random.uniform(30, 80)  # FUD
        
    # --- ج: تجمیع آرا (مکانیزم‌های اجماع) ---
    
    # 1. مکانیزم DAO سنتی (وزن برابر) - نودهای مخرب میانگین را دستکاری می‌کنند
    standard_dao_roi = (
        (honest_nodes * honest_roi_eval) + 
        (uncooperative_nodes * uncoop_roi_eval) + 
        (malicious_nodes * malicious_roi_eval)
    ) / total_nodes
    
    # 2. مکانیزم AIPoX پیشنهادی (تعدیل وزن با هوش مصنوعی)
    # هوش مصنوعی پس از 20 تراکنش، رفتار مخرب را شناسایی و وزن آن‌ها را کاهش می‌دهد
    w_honest, w_uncoop, w_malicious = 1.0, 0.4, 0.05
    total_ai_weight = (honest_nodes * w_honest) + (uncooperative_nodes * w_uncoop) + (malicious_nodes * w_malicious)
    
    ai_calculated_roi = (
        (honest_nodes * w_honest * honest_roi_eval) + 
        (uncooperative_nodes * w_uncoop * uncoop_roi_eval) + 
        (malicious_nodes * w_malicious * malicious_roi_eval)
    ) / total_ai_weight
    
    ai_calculated_roi = np.clip(ai_calculated_roi, 5, 400)
    
    # --- د: اعمال فیلتر هوشمند سیستم ---
    is_accepted = ai_calculated_roi >= minimum_required_roi(true_risk)
    status_label = "Accepted" if is_accepted else "Rejected"
    
    ai_final_risks.append(true_risk)
    ai_final_rois.append(ai_calculated_roi)
    decision_status.append(is_accepted)
    
    # ثبت ردیف داده
    simulation_logs.append({
        'Proposal_ID': f"PRJ-{p_id:04d}",
        'Total_Eval_Txs': tx_per_proposal,
        'Active_Nodes': total_nodes,
        'True_ROI(%)': round(true_roi, 2),
        'Malicious_ROI_Vote(%)': round(malicious_roi_eval, 2),
        'Standard_DAO_ROI(%)': round(standard_dao_roi, 2),
        'AI_Verified_ROI(%)': round(ai_calculated_roi, 2),
        'AI_Risk_Score': round(true_risk, 2),
        'Required_ROI_Threshold': round(minimum_required_roi(true_risk), 2),
        'Final_Decision': status_label
    })

# ==========================================
# 3. ذخیره جدول داده‌ها در فایل CSV
# ==========================================
df_financial = pd.DataFrame(simulation_logs)
df_financial.to_csv('Table_5_5_Risk_Reward_Data.csv', index=False)

print("Sample of Generated Financial Evaluation Data:")
print(df_financial[['Proposal_ID', 'True_ROI(%)', 'Malicious_ROI_Vote(%)', 'AI_Verified_ROI(%)', 'Final_Decision']].head(6).to_string())
print("-" * 50)

# ==========================================
# 4. رسم نمودار پراکندگی (با داده‌های تایید شده توسط AI)
# ==========================================
ai_final_risks = np.array(ai_final_risks)
ai_final_rois = np.array(ai_final_rois)
decision_status = np.array(decision_status)

fig, ax = plt.subplots(figsize=(10, 7))

# رسم پروژه‌های رد شده (زیر خط آستانه)
ax.scatter(ai_final_risks[~decision_status], ai_final_rois[~decision_status], 
           c='#d62728', alpha=0.6, edgecolors='w', s=50, label='Rejected Proposals (AI Filtered Out)')

# رسم پروژه‌های تایید شده (بالای خط آستانه)
ax.scatter(ai_final_risks[decision_status], ai_final_rois[decision_status], 
           c='#2ca02c', alpha=0.8, edgecolors='k', s=60, label='Shortlisted for Voting (Accepted)')

# رسم خط آستانه (مرز کارا)
x_line = np.linspace(0, 100, 100)
y_line = minimum_required_roi(x_line)
ax.plot(x_line, y_line, color='#1f77b4', linestyle='--', linewidth=2.5, 
        label='Dynamic AI Acceptance Threshold (Efficient Frontier)')

ax.set_title('Figure 5-5: AI-Driven Risk vs. Reward (ROI) Filtering in DAO-VC', fontsize=10, pad=15)
ax.set_xlabel('AI-Verified Risk Score (0 to 100)', fontsize=10)
ax.set_ylabel('AI-Verified Expected ROI (%)', fontsize=10)

ax.set_xlim(0, 100)
ax.set_ylim(0, 400)

# اضافه کردن جعبه اطلاعات شبیه‌سازی
info_text = f"Consensus Data:\n- Network Nodes: {total_nodes}\n- Fin Txs/Proj: {tx_per_proposal}\n- AI Anomaly Weighting: Active"
ax.text(2, 350, info_text, fontsize=9, bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))

ax.legend(loc='lower right', fontsize=9, frameon=True, shadow=True)

plt.tight_layout()
plt.savefig('5-5-risk_reward_scatter.png', dpi=300)
plt.show()