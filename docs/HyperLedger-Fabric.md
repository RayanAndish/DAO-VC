# دستورات نصب Hyperledger Fabric

برای اجرای کامل شبکه Hyperledger Fabric، مراحل نصب به ترتیب زیر انجام می‌شود. این موارد پیش از مراحل ایجاد شبکه (که قبلاً ذکر شدند) باید اجرا شوند:

## 1. نصب پیش‌نیازها

برای اجرای Fabric، پیش‌نیازهای زیر باید نصب شوند:

### 1.1. نصب git
sudo apt update
sudo apt install git -y

### 1.2. نصب cURL
sudo apt install curl -y

### 1.3. نصب Docker و Docker Compose
sudo apt install docker.io -y
sudo apt install docker-compose -y

### 1.4. نصب Go (نسخه 1.20 یا بالاتر)
wget https://go.dev/dl/go1.20.7.linux-amd64.tar.gz
sudo tar -xvf go1.20.7.linux-amd64.tar.gz -C /usr/local
echo "export PATH=$PATH:/usr/local/go/bin" >> ~/.bashrc
source ~/.bashrc

### 1.5. نصب Node.js (نسخه 16 یا 18)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

## 2. دانلود و نصب Hyperledger Fabric

### 2.1. کلون کردن مخزن fabric-samples
git clone https://github.com/hyperledger/fabric-samples.git
cd fabric-samples

### 2.2. دانلود باینری‌ها و تصاویر Docker
curl -sSL https://bit.ly/2ysbOFE | bash -s

## 3. تنظیم مسیرهای محیطی

### 3.1. افزودن مسیر باینری‌ها به متغیر PATH
export PATH=$PATH:$PWD/bin
echo "export PATH=\$PATH:$PWD/bin" >> ~/.bashrc

### 4. بازخوانی تغییرات محیطی
source ~/.bashrc
