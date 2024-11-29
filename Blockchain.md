#مستند مراحل ایجاد بلاکچین خصوصی بر اساس Hyperledger Fabric

##گام 1: آماده‌سازی محیط

**نصب پیش‌نیازها:**

'sudo apt update'
'sudo apt install -y curl docker.io docker-compose golang'

**فایل تنظیمات: نیاز به تنظیمات خاصی نیست.**

**خروجی: تایید نصب ابزارها و فایل‌های مرتبط.**

'sudo init 6'

**تنظیمات Docker:**

'sudo groupadd docker'
'sudo usermod -aG docker $USER'
'sudo systemctl start docker'
'sudo systemctl enable docker'

**فایل تنظیمات: نیاز به تنظیمات خاصی نیست.**

**دانلود Hyperledger Fabric Samples:**

'docker login -u errick60'
'dckr_pat_*****'
'curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/master/scripts/bootstrap.sh | bash -s'

**خروجی: پوشه fabric-samples در مسیر جاری.**

##گام 2: ایجاد فایل‌های اولیه

**ایجاد پوشه پروژه:**

'mkdir -p ~/fabric/{config,crypto-config,channel-artifacts}'

**کپی فایل‌های پیکربندی:**

'cp fabric-samples/config/* ~/fabric/config/'

**فایل تنظیمات:**

**مسیر فایل‌های تنظیمات: ~/fabric/config/configtx.yaml, ~/fabric/config/core.yaml**

##گام 3: تولید فایل‌های Crypto Material

**تولید Crypto Material:**

'/home/errick/fabric/bin/cryptogen generate --config=/home/errick/fabric/config/crypto-config.yaml --output=/home/errick/fabric/crypto-config'
'

**فایل تنظیمات:**

**مسیر: ~/fabric/config/crypto-config.yaml**

خروجی: پوشه‌های ordererOrganizations و peerOrganizations در مسیر crypto-config.

##گام 4: ایجاد بلاک جنسیس

**تولید بلاک جنسیس:**

**تعریف مسیر فایل کانفیگ**

'export FABRIC_CFG_PATH=/home/errick/fabric/config'
'/home/errick/fabric/bin/configtxgen -profile DAOGenesis -outputBlock /home/errick/fabric/channel-artifacts/genesis.block -channelID system-channel'

**فایل تنظیمات:**

**مسیر: ~/fabric/config/configtx.yaml**

خروجی: فایل genesis.block در پوشه channel-artifacts.

**ایجاد فایل تراکنش کانال:**

'/home/errick/fabric/bin/configtxgen -profile DAOChannel -outputCreateChannelTx /home/errick/fabric/channel-artifacts/channel.tx -channelID dao-channel'

**فایل تنظیمات:**

**مسیر: ~/fabric/config/configtx.yaml**

##گام 5: تنظیمات Docker Compose

**ویرایش فایل docker-compose.yaml: فایل docker-compose.yaml را بر اساس تنظیمات و نودهای موردنظر قرار دهید.

**مسیر فایل: ~/fabric/docker-compose.yaml**

**ایجاد نودها:

'docker-compose -f /home/errick/fabric/config/docker-compose.yaml up -d'

خروجی: کانتینرهای Orderer و Peer فعال شوند.

##گام 6: راه‌اندازی Orderer و ایجاد کانال

**استارت Orderer:**

'docker exec -it fabric-orderer1.dao-vc.ir orderer'

**فایل تنظیمات:**

**مسیر: /etc/hyperledger/fabric/config/configtx.yaml**

**مسیر Crypto: /etc/hyperledger/fabric/crypto**

**ایجاد کانال:**

'docker exec -it fabric-peer0.org1.dao-vc.ir peer channel create -o fabric-orderer1.dao-vc.ir:7150 -c dao-channel -f /etc/hyperledger/fabric/channel-artifacts/channel.tx --outputBlock /etc/hyperledger/fabric/channel-artifacts/dao-channel.block --tls --cafile /etc/hyperledger/fabric/crypto/ordererOrganizations/dao-vc.ir/orderers/orderer1.dao-vc.ir/tls/ca.crt'

**فایل تنظیمات:**

**فایل channel.tx و genesis.block در مسیر /etc/hyperledger/fabric/channel-artifacts/**

##گام 7: اتصال Peerها به کانال

**اتصال Peer0:**

'docker exec -it fabric-peer0.org1.dao-vc.ir peer channel join -b /etc/hyperledger/fabric/channel-artifacts/dao-channel.block'

**فایل تنظیمات:**

**مسیر بلاک: /etc/hyperledger/fabric/channel-artifacts/dao-channel.block**

**اتصال Peerهای دیگر: برای هر Peer مشابه دستور بالا اجرا کنید.**

##گام 8: بررسی و اطمینان

**لیست کانال‌ها:**

'docker exec -it fabric-peer0.org1.dao-vc.ir peer channel list'

خروجی: نمایش کانال dao-channel.

**بررسی لاگ‌ها:**

'docker logs fabric-peer0.org1.dao-vc.ir'
'docker logs fabric-orderer1.dao-vc.ir'

**نکته: در هر مرحله، مسیرها و پورت‌ها را با فایل‌های پیکربندی تطبیق دهید.