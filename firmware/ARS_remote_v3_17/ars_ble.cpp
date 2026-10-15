#include "ars_ble.h"
#include <Arduino.h>
#include <bluefruit.h>
#include <string.h>

namespace ArsBle {
static constexpr uint16_t COMPANY=0xFFFF;
static constexpr uint8_t MAGIC=0xA6, STATE=0x30, RESULT=0x31;
static constexpr uint32_t STATE_TIMEOUT_MS=15000, TX_BURST_MS=400;
static volatile uint8_t room=1,seat=0,q=0,options=0;
static volatile bool open=false,haveState=false,stateEvent=false,ackEvent=false;
static volatile uint32_t session=0,lastStateMs=0,notReadyUntil=0;
static volatile uint8_t ackStatus=0;
static bool txValid=false,txScheduled=false,txOn=false;
static volatile bool rxPaused=false;
static uint32_t nextRxRetry=0;
static uint8_t tx[21]={},attempts=0;
static uint32_t txDue=0,txStop=0;
#define LOCK() taskENTER_CRITICAL()
#define UNLOCK() taskEXIT_CRITICAL()

static uint32_t read32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24;
}
static void put32(uint8_t* p,uint32_t v) {
    for(uint8_t i=0;i<4;i++)p[i]=uint8_t(v>>(8*i));
}
static void printToken() {
    const char* hex="0123456789abcdef";
    for(uint8_t i=13;i<21;i++){Serial.print(hex[tx[i]>>4]);Serial.print(hex[tx[i]&15]);}
}

static void scanCallback(ble_gap_evt_adv_report_t* report) {
    uint8_t msd[32]={};
    uint8_t len=Bluefruit.Scanner.parseReportByType(report,BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC_DATA,msd,sizeof(msd));
    if(len>=5 && msd[0]==0xFF && msd[1]==0xFF && msd[2]==MAGIC) {
        const uint8_t* p=msd+2;uint8_t n=len-2;
        LOCK();
        if(p[2]==room && p[1]==STATE && n==10 && p[3]<=99 && p[4]<=1 && p[5]<=10) {
            uint32_t sid=read32(p+6);
            // Force application to drop login/pending state on a session switch.
            if(haveState && sid!=session)notReadyUntil=millis()+100;
            bool changed=!haveState || (uint32_t)(millis()-lastStateMs)>=STATE_TIMEOUT_MS || sid!=session || q!=p[3] || open!=(p[4]!=0) || options!=p[5];
            session=sid;q=p[3];open=p[4]!=0;options=p[5];
            lastStateMs=millis();haveState=true;
            if(changed)stateEvent=true; // duplicate heartbeat refreshes freshness without Serial spam
        } else if(p[2]==room && p[1]==RESULT && n>=4 && p[3]>=1 && p[3]<=2 && n==4+p[3]*9 && txValid) {
            for(uint8_t i=0;i<p[3];i++) {
                const uint8_t* rec=p+4+i*9;
                if(memcmp(rec,tx+13,8)==0) {
                    ackStatus=rec[8];ackEvent=true;break;
                }
            }
        }
        UNLOCK();
    }
    if(!rxPaused)Bluefruit.Scanner.resume();
}

static void restoreRx() {
    rxPaused=false;
    if(!Bluefruit.Scanner.isRunning()) {
        bool ok=Bluefruit.Scanner.start(0);
        nextRxRetry=millis()+250;
        if(!ok)Serial.println("ADV RX START FAILED: retry in 250 ms");
    }
}
static void endBurst() {
    Bluefruit.Advertising.stop();txOn=false;
    restoreRx();
    Serial.print("ADV_RX_RESUME uptime_ms=");Serial.println(millis());
}

void begin(uint8_t r,uint8_t s) {
    room=r;seat=s;
    Bluefruit.begin(1,0);Bluefruit.autoConnLed(false);
    Bluefruit.setName("ARS_ADV17");Bluefruit.setTxPower(0);
    Bluefruit.Scanner.setRxCallback(scanCallback);
    Bluefruit.Scanner.setInterval(160,160);Bluefruit.Scanner.useActiveScan(false);
    Bluefruit.Scanner.start(0);
}

bool ready() {
    return haveState && session!=0 && (uint32_t)(millis()-lastStateMs)<STATE_TIMEOUT_MS &&
           (!notReadyUntil || (int32_t)(millis()-notReadyUntil)>=0);
}

void finishTransaction() {
    txScheduled=false;endBurst();
    LOCK();txValid=false;ackEvent=false;UNLOCK();
}

void setIdentity(uint8_t r,uint8_t s) {
    finishTransaction();
    LOCK();room=r;seat=s;haveState=stateEvent=false;session=0;notReadyUntil=0;UNLOCK();
}

bool sendPacket(uint8_t typ,uint8_t r,uint8_t s,uint8_t question,uint8_t seq,uint8_t ans,uint16_t batt) {
    if(!ready() || r!=room || s!=seat || (typ!=1 && typ!=2))return false;
    if(!txValid) {
        uint8_t token[8]={};
        if(sd_rand_application_vector_get(token,sizeof(token))!=NRF_SUCCESS)return false;
        bool nonzero=false;for(auto b:token)nonzero|=b!=0;if(!nonzero)return false;
        LOCK();
        tx[0]=MAGIC;tx[1]=typ;tx[2]=r;tx[3]=s;tx[4]=question;tx[5]=seq;tx[6]=ans;
        tx[7]=batt&255;tx[8]=batt>>8;put32(tx+9,session);memcpy(tx+13,token,8);
        txValid=true;ackEvent=false;UNLOCK();
        attempts=0;
        Serial.print("ADV_BEGIN token=");printToken();Serial.print(" type=");Serial.print(typ);
        Serial.print(" uptime_ms=");Serial.println(millis());
    } else if(tx[1]!=typ || tx[2]!=r || tx[3]!=s || tx[4]!=question || tx[5]!=seq || tx[6]!=ans) {
        return false; // cannot mutate an in-flight transaction
    }
    attempts++;
    txDue=millis()+uint32_t(random(201));txScheduled=true;
    return true;
}

void update() {
    // RX callbacks run in the BLE task. Only the application task changes TX scheduling.
    if(ackEvent && (txOn || txScheduled)) {
        txScheduled=false;endBurst();
    }
    if(txOn && (int32_t)(millis()-txStop)>=0)endBurst();
    if(!txOn && !rxPaused && !Bluefruit.Scanner.isRunning() && (int32_t)(millis()-nextRxRetry)>=0)restoreRx();
    if(txScheduled && (int32_t)(millis()-txDue)>=0) {
        txScheduled=false;
        uint8_t msd[23]={0xFF,0xFF};memcpy(msd+2,tx,sizeof(tx));
        // One role at a time on nRF: bounded TX, then return to STATE/ACK RX.
        rxPaused=true;
        if(!Bluefruit.Scanner.stop()) {
            Serial.println("ADV RX STOP FAILED: skip burst and retry same transaction");
            restoreRx();return;
        }
        Bluefruit.Advertising.stop();Bluefruit.Advertising.clearData();
        Bluefruit.Advertising.setType(BLE_GAP_ADV_TYPE_NONCONNECTABLE_NONSCANNABLE_UNDIRECTED);
        Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
        Bluefruit.Advertising.addManufacturerData(msd,sizeof(msd));
        Bluefruit.Advertising.setInterval(160,160); // 100 ms, plus controller jitter
        txOn=Bluefruit.Advertising.start(0);txStop=millis()+TX_BURST_MS;
        if(!txOn) {
            Serial.println("ADV TX START FAILED: will retry same transaction");
            restoreRx();
        } else {
            Serial.print("ADV_TX_START token=");printToken();Serial.print(" attempt=");Serial.print(attempts);
            Serial.print(" uptime_ms=");Serial.println(millis());
        }
    }
}

bool takeLoginAck(uint8_t& seq,uint8_t& status) {
    LOCK();bool ok=ackEvent && txValid && tx[1]==1;
    if(ok){seq=tx[5];status=ackStatus;ackEvent=false;}UNLOCK();return ok;
}
bool takeAnswerAck(uint8_t& question,uint8_t& seq,uint8_t& ans,uint8_t& status) {
    LOCK();bool ok=ackEvent && txValid && tx[1]==2;
    if(ok){question=tx[4];seq=tx[5];ans=tx[6];status=ackStatus;ackEvent=false;}UNLOCK();return ok;
}
bool takeStateUpdate(uint8_t& question,bool& op,uint8_t& n) {
    LOCK();bool ok=stateEvent;
    if(ok){question=q;op=open;n=options;stateEvent=false;}UNLOCK();return ok;
}
bool takeOpenMask(uint64_t&) {return false;}
void reportOutcome(uint16_t status,uint32_t elapsedMs) {
    if(!txValid)return;
    Serial.print("ADV_METRIC token=");printToken();Serial.print(" type=");Serial.print(tx[1]);
    Serial.print(" status=");Serial.print(status);Serial.print(" elapsed_ms=");Serial.print(elapsedMs);
    Serial.print(" attempts=");Serial.print(attempts);
    Serial.print(" uptime_ms=");Serial.println(millis());
}
} // namespace ArsBle
