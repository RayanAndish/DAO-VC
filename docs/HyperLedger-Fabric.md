markdown
# دستورات نصب Hyperledger Fabric
برای اجرای کامل شبکه Hyperledger Fabric، مراحل نصب به ترتیب زیر انجام می‌شود. این موارد پیش از مراحل ایجاد شبکه (که قبلاً ذکر شدند) باید اجرا شوند:

1. نصب پیش‌نیازها
برای اجرای Fabric، پیش‌نیازهای زیر باید نصب شوند:

Git:

sudo apt update
sudo apt install git -y
cURL:

bash
sudo apt install curl -y
Docker و Docker Compose:

bash
sudo apt install docker.io -y
sudo apt install docker-compose -y
Go (نسخه 1.20 یا بالاتر):

bash
wget https://go.dev/dl/go1.20.7.linux-amd64.tar.gz
sudo tar -xvf go1.20.7.linux-amd64.tar.gz -C /usr/local
echo "export PATH=$PATH:/usr/local/go/bin" >> ~/.bashrc
source ~/.bashrc
Node.js(نسخه 16 یا 18):

bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
دانلود و نصب Hyperledger Fabric کلون کردن مخزن fabric-samples:

bash
git clone https://github.com/hyperledger/fabric-samples.git
cd fabric-samples
دانلود باینری‌ها و تصاویر Docker:

bash
curl -sSL https://bit.ly/2ysbOFE | bash -s
تنظیم مسیرهای محیطی افزودن مسیر باینری‌ها به متغیر PATH:

bash
export PATH=$PATH:$PWD/bin
echo "export PATH=\$PATH:$PWD/bin" >> ~/.bashrc
بازخوانی تغییرات محیطی:

bash
source ~/.bashrc