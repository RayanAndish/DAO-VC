import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import scipy.stats as stats

# تنظیمات استایل و گرافیک
plt.style.use('seaborn-v0_8-whitegrid')
np.random.seed(42) # برای ثابت ماندن نتایج

# پارامترهای شبیه‌سازی بر اساس معماری
n_proposals = 1000
tx_per_proposal = 20 # هر تصمیم شامل 20 تراکنش مستقل است
total_nodes = 100    # در این سناریوی متراکم، 100 نود فعال در نظر گرفته شده است

# شبیه‌سازی ترکیب نودها در شبکه (ثابت در طول این چرخه)
malicious_nodes = int(total_nodes * 0.15)    # 15 نود مخرب (سعی در دستکاری ریسک دارند)
uncooperative_nodes = int(total_nodes * 0.20)# 20 نود غیرهمکار (رأی تصادفی یا بی‌دقت)
honest_nodes = total_nodes - malicious_nodes - uncooperative_nodes # 65 نود صادق

simulation_logs = []
final_ai_risk_scores = []

# ==========================================
# 1. موتور شبیه‌سازی ارزیابی ریسک توسط نودها و AI
# ==========================================
for p_id in range(1, n_proposals + 1):
    
    # ریسک ذاتی و واقعی پروژه (توزیع نرمال حول 65)
    true_risk = np.random.normal(loc=65, scale=15)
    true_risk = np.clip(true_risk, 5, 95)
    
    # --- رفتار نودها در 20 تراکنش ارزیابی ---
    # نودهای صادق: ریسک را با دقت بالایی (نزدیک به واقعیت) تخمین می‌زنند
    honest_eval = true_risk + np.random.normal(0, 3)
    
    # نودهای غیرهمکار: ارزیابی با خطای بالا و نویز زیاد
    uncoop_eval = true_risk + np.random.normal(0, 15)
    
    # نودهای مخرب: سعی می‌کنند ریسک پروژه‌های پرخطر را کم، و پروژه‌های امن را زیاد جلوه دهند (حمله دستکاری)
    if true_risk > 70:
        malicious_eval = true_risk - np.random.uniform(20, 40) # سعی در پنهان کردن ریسک
    else:
        malicious_eval = true_risk + np.random.uniform(20, 40) # سعی در تخریب پروژه خوب
        
    # --- مکانیزم DAO استاندارد (بدون هوش مصنوعی) ---
    # میانگین‌گیری ساده (وزن برابر برای همه 100 نود) - مخرب‌ها موفق به تغییر نتیجه می‌شوند
    standard_dao_risk = (
        (honest_nodes * honest_eval) + 
        (uncooperative_nodes * uncoop_eval) + 
        (malicious_nodes * malicious_eval)
    ) / total_nodes
    
    # --- مکانیزم DAO-VC پیشنهادی (AIPoX) ---
    # هوش مصنوعی رفتار مخرب و نویز را تشخیص داده و وزن آن‌ها را به شدت کاهش می‌دهد (مثلا ضریب 0.1 و 0.4)
    w_honest, w_uncoop, w_malicious = 1.0, 0.4, 0.1
    total_ai_weight = (honest_nodes * w_honest) + (uncooperative_nodes * w_uncoop) + (malicious_nodes * w_malicious)
    
    ai_calculated_risk = (
        (honest_nodes * w_honest * honest_eval) + 
        (uncooperative_nodes * w_uncoop * uncoop_eval) + 
        (malicious_nodes * w_malicious * malicious_eval)
    ) / total_ai_weight
    
    ai_calculated_risk = np.clip(ai_calculated_risk, 0, 100)
    final_ai_risk_scores.append(ai_calculated_risk)
    
    # ثبت در جدول داده‌ها
    simulation_logs.append({
        'Proposal_ID': f"PRJ-{p_id:04d}",
        'Total_Eval_Txs': tx_per_proposal,
        'Network_Nodes': total_nodes,
        'Honest_Nodes': honest_nodes,
        'Malicious_Nodes': malicious_nodes,
        'True_Inherent_Risk': round(true_risk, 2),
        'Malicious_Nodes_Vote': round(malicious_eval, 2),
        'Standard_DAO_Score': round(standard_dao_risk, 2),
        'Final_AI_Risk_Score': round(ai_calculated_risk, 2),
        'AI_Correction_Delta': round(abs(ai_calculated_risk - standard_dao_risk), 2)
    })

# ایجاد دیتافریم و ذخیره فایل CSV (شامل 1000 ردیف پروپوزال)
df_risk = pd.DataFrame(simulation_logs)
df_risk.to_csv('Table_5_4_Risk_Evaluation_Data.csv', index=False)

print("Sample of Generated AI Risk Evaluation Data (First 5 Proposals):")
print(df_risk[['Proposal_ID', 'True_Inherent_Risk', 'Malicious_Nodes_Vote', 'Standard_DAO_Score', 'Final_AI_Risk_Score']].head().to_string())
print("-" * 50)

# ==========================================
# 2. رسم نمودار (با داده‌های خروجی )
# ==========================================
risk_scores_array = np.array(final_ai_risk_scores)

fig, ax = plt.subplots(figsize=(11, 6))

count, bins, ignored = ax.hist(risk_scores_array, bins=25, density=False, alpha=0.7, 
                               color='#4c72b0', edgecolor='black', linewidth=1.2,
                               label='Number of Proposals (AI Evaluated)')

bin_width = bins[1] - bins[0]
x = np.linspace(0, 100, 100)
pdf = stats.norm.pdf(x, loc=np.mean(risk_scores_array), scale=np.std(risk_scores_array))
ax.plot(x, pdf * n_proposals * bin_width, color='#c44e52', linewidth=3, label='Normal Distribution Fit')

ax.axvspan(0, 33, alpha=0.15, color='green', label='Low Risk Zone (0-33)')
ax.axvspan(33, 66, alpha=0.15, color='yellow', label='Medium Risk Zone (34-66)')
ax.axvspan(66, 100, alpha=0.15, color='red', label='High Risk Zone (67-100)')

ax.set_title('Figure 5-4: Distribution of AI-Verified Project Risk Scores (N=1000)', fontsize=14, pad=15)
ax.set_xlabel('Final AI Risk Score (0: Risk-Free to 100: Extreme Risk)', fontsize=12)
ax.set_ylabel('Number of Proposals', fontsize=12)

ax.set_xlim(0, 100)
ax.set_xticks(np.arange(0, 101, 10))

# اضافه کردن جعبه اطلاعات شبیه‌سازی شبکه
info_text = f"Network Config:\nTotal Nodes: {total_nodes}\nEvaluation Txs/Proj: {tx_per_proposal}\nAI Weighting Applied"
ax.text(3, 85, info_text, fontsize=9, bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))

ax.legend(loc='upper left', fontsize=10, frameon=True, shadow=True)

plt.tight_layout()
plt.savefig('5-4-risk_distribution_chart.png', dpi=300)
plt.show()