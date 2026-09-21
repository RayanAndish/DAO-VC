import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

plt.style.use('seaborn-v0_8-whitegrid')
np.random.seed(42)

# ==========================================
# 1. تنظیمات جامعه کاربری و شبکه (گسسته)
# ==========================================
total_nodes = 100
tx_per_proposal = 20

simulation_logs = []

# --- الف: توزیع ثروت (توکن) بین 100 نود واقعی ---
# استفاده از توزیع پارتو برای ایجاد نهنگ‌ها (قانون 80/20)
token_balances = np.random.pareto(a=1.1, size=total_nodes) * 1000

# برای اینکه نهنگ‌ها خیلی مصنوعی بزرگ نشوند، سقف می‌گذاریم
token_balances = np.clip(token_balances, 10, 50000)

# مرتب‌سازی نودها از فقیرترین به ثروتمندترین (پیش‌نیاز رسم منحنی لورنز)
token_balances = np.sort(token_balances)

# --- ب: تخصیص رفتار به نودها ---
# 65 صادق، 20 غیرهمکار، 15 مخرب
behaviors = ['Honest'] * 65 + ['Uncooperative'] * 20 + ['Malicious'] * 15
# رفتارها را تصادفی بین افراد پخش می‌کنیم
np.random.shuffle(behaviors)

# سناریو: 3 تا از 5 نهنگِ برترِ شبکه، غیرهمکار یا مخرب هستند
behaviors[-1] = 'Malicious'      # بزرگترین نهنگ (رتبه 100) مخرب است
behaviors[-2] = 'Uncooperative'  # دومین نهنگ غیرهمکار است
behaviors[-4] = 'Malicious'      # چهارمین نهنگ مخرب است
behaviors[-5] = 'Honest'         # پنجمین نهنگ صادق است

# ==========================================
# 2. موتور شبیه‌سازی هوش مصنوعی و محاسبه قدرت رأی
# ==========================================
for i in range(total_nodes):
    node_id = f"Node_{i+1:03d}"
    tokens = token_balances[i]
    behavior = behaviors[i]
    
    # 1. قدرت در DAO استاندارد (Pure dPoS)
    standard_power_raw = tokens
    
    # 2. ارزیابی هوش مصنوعی در طول 20 تراکنش (PoP Score)
    if behavior == 'Honest':
        pop_score = np.random.uniform(0.9, 1.0)
    elif behavior == 'Uncooperative':
        pop_score = np.random.uniform(0.2, 0.5)
    else: # Malicious
        pop_score = np.random.uniform(0.01, 0.1) # جریمه سنگین AI
        
    # 3. قدرت در سیستم AIPoX (ترکیب ثروت و مشارکت)
    # این فرمول باعث می‌شود یک نهنگ مخرب نتواند با پول، قدرت را بخرد
    aipox_power_raw = (tokens ** 0.29) * pop_score
    
    simulation_logs.append({
        'Node_ID': node_id,
        'Token_Balance': round(tokens, 2),
        'Behavior_in_Txs': behavior,
        'AI_PoP_Score(0_to_1)': round(pop_score, 3),
        'Standard_Power_Raw': standard_power_raw,
        'AIPoX_Power_Raw': aipox_power_raw
    })

df_governance = pd.DataFrame(simulation_logs)

# ==========================================
# 3. محاسبه تجمعی (Cumulative) برای رسم منحنی لورنز
# ==========================================
df_governance['Standard_Power(%)'] = (df_governance['Standard_Power_Raw'] / df_governance['Standard_Power_Raw'].sum()) * 100
df_governance['AIPoX_Power(%)'] = (df_governance['AIPoX_Power_Raw'] / df_governance['AIPoX_Power_Raw'].sum()) * 100

# محاسبه مجموع تجمعی قدرت
df_governance['Cum_Standard_Power'] = df_governance['Standard_Power(%)'].cumsum()
df_governance['Cum_AIPoX_Power'] = df_governance['AIPoX_Power(%)'].cumsum()
# محور X (درصد جمعیت از 1 تا 100)
df_governance['Cum_Population'] = np.linspace(1, 100, total_nodes) 

# ==========================================
# 4. رسم نمودار لورنز (گسسته و ارگانیک)
# ==========================================
# اضافه کردن نقطه (0,0) برای شروع اصولی نمودار
x_pop = np.insert(df_governance['Cum_Population'].values, 0, 0) 
y_perfect = x_pop
y_standard = np.insert(df_governance['Cum_Standard_Power'].values, 0, 0)
y_aipox = np.insert(df_governance['Cum_AIPoX_Power'].values, 0, 0)

fig, ax = plt.subplots(figsize=(9, 9))

ax.plot(x_pop, y_perfect, linestyle='--', color='gray', label='Line of Perfect Equality (1 User = 1 Vote)')

# کشیدن خط استاندارد با دندانه‌های واقعی
ax.plot(x_pop, y_standard, color='#d62728', linewidth=2.5, label='Standard Token-Voting (Pure dPoS)')

# کشیدن خط AIPoX با دندانه‌های واقعی
ax.plot(x_pop, y_aipox, color='#9467bd', linewidth=3, label='Proposed AIPoX (AI-Weighted dPoS + PoP)')

ax.fill_between(x_pop, y_standard, y_aipox, color='#9467bd', alpha=0.15, 
                label='Power Shifted to Honest/Active Nodes via AI')

ax.set_title('Figure 5-3: Voting Power Distribution (Lorenz Curve Analysis)', fontsize=14, pad=15)
ax.set_xlabel('Cumulative Share of Active Nodes (from Poorest to Richest) %', fontsize=10)
ax.set_ylabel('Cumulative Share of Voting Power in Consensus %', fontsize=10)

ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.set_aspect('equal', adjustable='box')

info_text = f"Governance Params:\n- Total Nodes: {total_nodes} (Discrete)\n- Txs Evaluated: {tx_per_proposal}\n- Wealth Dist: Pareto (Whales)\n- AI Slashing: Active"
ax.text(2, 78, info_text, fontsize=9, bbox=dict(facecolor='white', alpha=0.9, edgecolor='gray'))

ax.legend(loc='upper left', fontsize=9, frameon=True, shadow=True)

plt.tight_layout()
plt.savefig('5-3-voting_power_distribution_realistic.png', dpi=300)
plt.show()

# ذخیره جدول داده‌ها
output_cols = ['Node_ID', 'Cum_Population', 'Token_Balance', 'Behavior_in_Txs', 'AI_PoP_Score(0_to_1)', 'Standard_Power(%)', 'AIPoX_Power(%)']
df_governance[output_cols].to_csv('Table_5_3_Voting_Power_Data.csv', index=False)