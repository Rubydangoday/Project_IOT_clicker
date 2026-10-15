#pragma once
#include "Arduino.h"
#include <cstring>
#define BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE 2
#define BLE_GAP_ADV_TYPE_NONCONNECTABLE_NONSCANNABLE_UNDIRECTED 3
#define BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC_DATA 0xff
#define NRF_SUCCESS 0
#define taskENTER_CRITICAL() do{}while(0)
#define taskEXIT_CRITICAL() do{}while(0)
inline bool fakeRandFail=false,fakeAdRunning=false,fakeAdFail=false,fakeScanFail=false,fakeScanStopFail=false;
inline uint64_t fakeNonce=0;
inline uint32_t sd_rand_application_vector_get(uint8_t* p,uint8_t n){
 if(fakeRandFail)return 1;
 ++fakeNonce;for(uint8_t i=0;i<n;i++)p[i]=uint8_t(fakeNonce>>(8*(i%8)));return 0;
}
struct ble_gap_evt_adv_report_t {std::vector<uint8_t> msd;};
inline std::vector<std::vector<uint8_t>> fakeAds;
struct AdvertisingMock {
 std::vector<uint8_t> data;
 void addFlags(int){}void setInterval(int,int){}void setType(int){}
 bool addManufacturerData(const void* p,uint8_t n){data.assign((const uint8_t*)p,(const uint8_t*)p+n);return true;}
 bool start(int){if(fakeAdFail)return false;fakeAdRunning=true;fakeAds.push_back(data);return true;}
 bool stop(){fakeAdRunning=false;return true;}
 void clearData(){data.clear();}
};
struct ScannerMock {
 void(*callback)(ble_gap_evt_adv_report_t*)=nullptr;
 bool running=false;
 void setRxCallback(void(*cb)(ble_gap_evt_adv_report_t*)){callback=cb;}
 void setInterval(int,int){}void useActiveScan(bool){}
 bool start(int){if(fakeScanFail)return false;running=true;return true;}
 bool stop(){if(fakeScanStopFail)return false;running=false;return true;}
 bool isRunning(){return running;}
 bool resume(){running=true;return true;}
 uint8_t parseReportByType(ble_gap_evt_adv_report_t* p,int,uint8_t* out,uint8_t n){
  uint8_t len=p->msd.size()<n?p->msd.size():n;memcpy(out,p->msd.data(),len);return len;
 }
};
struct BluefruitMock {
 AdvertisingMock Advertising;ScannerMock Scanner;
 void begin(int,int){}void autoConnLed(bool){}void setName(const char*){}void setTxPower(int){}
};
inline BluefruitMock Bluefruit;
