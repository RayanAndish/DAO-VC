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

# مراحل ایجاد شبکه بلاکچین خصوصی با استفاده از Hyperledger Fabric

برای مرور کامل مراحل، تمامی گام‌ها بدون ذکر محتوای دقیق فایل‌ها و فقط با ذکر نام فایل‌ها و مسیرهای مربوطه به شرح زیر هستند:

## 1. آماده‌سازی پیش‌نیازها
اطمینان حاصل کنید که ابزارهای Fabric (مانند cryptogen, configtxgen, و peer) نصب شده‌اند.
تنظیم مسیر FABRIC_CFG_PATH به دایرکتوری پروژه:
export FABRIC_CFG_PATH=/home/errick/DAO-VC

## 2. ایجاد کلیدها و گواهی‌ها
اجرای ابزار cryptogen برای تولید کلیدها و گواهی‌های مورد نیاز:
./cryptogen generate --config=/home/errick/DAO-VC/crypto-config.yaml
مسیر فایل‌ها: /home/errick/DAO-VC/crypto-config/

## 3. تولید فایل Genesis Block
اجرای ابزار configtxgen برای ایجاد بلاک جنسیس:
./configtxgen -profile DAOGenesis -outputBlock /home/errick/DAO-VC/channel-artifacts/genesis.block -channelID DAOChannel -configPath /home/errick/DAO-VC
مسیر فایل‌ها: /home/errick/DAO-VC/channel-artifacts/genesis.block

## 4. ایجاد فایل تعریف کانال
تولید فایل تراکنش کانال:
./configtxgen -profile DAOChannel -outputCreateChannelTx /home/errick/DAO-VC/channel-artifacts/channel.tx -channelID DAOChannel -configPath /home/errick/DAO-VC
مسیر فایل‌ها: /home/errick/DAO-VC/channel-artifacts/channel.tx

## 5. راه‌اندازی Orderer
تنظیمات و راه‌اندازی Orderer با استفاده از فایل‌های موجود در:
فایل تنظیمات Orderer: /home/errick/DAO-VC/configtx.yaml
گواهی‌های Orderer: /home/errick/DAO-VC/crypto-config/ordererOrganizations/

## 6. ایجاد Peer
راه‌اندازی Peer:
فایل تنظیمات Peer: /home/errick/DAO-VC/core.yaml
گواهی‌ها و کلیدهای مرتبط: /home/errick/DAO-VC/crypto-config/peerOrganizations/

## 7. ایجاد کانال
اجرای دستور برای ایجاد کانال:
./peer channel create -o localhost:7050 -c DAOChannel -f /home/errick/DAO-VC/channel-artifacts/channel.tx --outputBlock /home/errick/DAO-VC/channel-artifacts/DAOChannel.block --tls --cafile /home/errick/DAO-VC/crypto-config/ordererOrganizations/dao-vc.ir/tlsca/tlsca.dao-vc.ir-cert.pem
فایل‌های کانال: /home/errick/DAO-VC/channel-artifacts/DAOChannel.block

## 8. پیوستن Peerها به کانال
اضافه کردن Peerها به کانال با دستور زیر:
./peer channel join -b /home/errick/DAO-VC/channel-artifacts/DAOChannel.block

## 9. نصب Chaincode
نصب و تایید Chaincode برای اجرا بر روی شبکه:
مسیر Chaincode: /home/errick/DAO-VC/chaincode/

## 10. تست شبکه
اجرای تست‌ها و بررسی سلامت شبکه:
تعامل با شبکه از طریق peer و بررسی عملکرد Orderer و Peerها.
تایید تراکنش‌ها و کانال‌ها.

### فایل‌های اصلی و مسیرها
| فایل/پوشه            | مسیر                                    |
|----------------------|-----------------------------------------|
| `crypto-config.yaml` | `/home/errick/DAO-VC/`                  |
| `configtx.yaml`      | `/home/errick/DAO-VC/`                  |
| `channel-artifacts/` | `/home/errick/DAO-VC/channel-artifacts/`|
| `crypto-config/`     | `/home/errick/DAO-VC/crypto-config/`    |
| `core.yaml`          | `/home/errick/DAO-VC/`                  |
| `chaincode/`         | `/home/errick/DAO-VC/chaincode/`        |
