#include <cassert>
#include <iostream>
#include <bluefruit.h>
#include "../../firmware/ARS_remote_v3_17/ARS_remote_v3_17.ino"
static void receive(std::vector<uint8_t> data) {
 if(!Bluefruit.Scanner.running)return;
 data.insert(data.begin(),{0xff,0xff});ble_gap_evt_adv_report_t report{data};
 Bluefruit.Scanner.callback(&report);
}
static void state(uint8_t question,bool op,uint32_t sid=1,uint8_t r=1) {
 receive({0xa6,0x30,r,question,(uint8_t)op,4,(uint8_t)sid,(uint8_t)(sid>>8),(uint8_t)(sid>>16),(uint8_t)(sid>>24)});
}
static void run(uint32_t ms,bool heartbeat=true,uint8_t question=1,bool op=true,uint32_t sid=1) {
 uint32_t start=millis(),last=millis();
 while((uint32_t)(millis()-start)<ms) {
  if(heartbeat && millis()-last>=1000){state(question,op,sid);last=millis();}
  auto t=millis();loop();assert(!(fakeAdRunning && Bluefruit.Scanner.running));if(t==millis())fakeMillis++;
 }
}
static std::vector<uint8_t> token() {
 assert(!fakeAds.empty());auto& ad=fakeAds.back();assert(ad.size()==23);
 return {ad.begin()+15,ad.begin()+23};
}
static void ack(std::vector<uint8_t> tok,uint8_t status=0,uint8_t r=1) {
 if(fakeAdRunning)run(420,false);
 std::vector<uint8_t> data={0xa6,0x31,r,1};data.insert(data.end(),tok.begin(),tok.end());data.push_back(status);receive(data);loop();
}
int main() {
 fakeMillis=100;displayBegin();statusLedBegin();keypadBegin();gRoom=1;gSeat=2;ArsBle::begin(1,2);
 beginLogin();assert(pending.kind==PENDING_NONE);
 run(100,false);assert(!ArsBle::ready());
 state(1,true);run(10);assert(pending.kind==PENDING_LOGIN);
 auto login=token();assert(fakeAdRunning && !Bluefruit.Scanner.running);
 // A queued callback must not resume scanning inside a burst.
 ble_gap_evt_adv_report_t queued{{0xff,0xff}};Bluefruit.Scanner.callback(&queued);
 assert(!Bluefruit.Scanner.running);
 ack(login);assert(loggedIn && pending.kind==PENDING_NONE);
 handleKey(KEY_2_B);handleKey(KEY_OK);run(10);assert(pending.kind==PENDING_ANSWER);
 auto first=token();assert(first!=login);auto seq=pending.seq;
 ack(login);assert(pending.kind==PENDING_ANSWER); // stale token cannot ACK answer
 ack(first,0,2);assert(pending.kind==PENDING_ANSWER); // other room cannot ACK
 auto before=fakeAds.size();run(3000);assert(fakeAds.size()>before && token()==first && pending.seq==seq);
 run(420,false);assert(Bluefruit.Scanner.running && !fakeAdRunning); // TX ends before ACK listening
 ack(first);assert(pending.kind==PENDING_NONE && selectedAnswer==0);
 // Fresh click uses fresh token even with recycled seq and identical answer.
 seqNo=uint8_t(seq-1);handleKey(KEY_2_B);handleKey(KEY_OK);run(10);
 assert(token()!=first && pending.seq==seq);ack(first);assert(pending.kind==PENDING_ANSWER);
 auto second=token();run(420,false);state(1,false);loop();assert(pending.kind==PENDING_ANSWER);
 ack(second,2);assert(pending.kind==PENDING_NONE && !questionAnswerable());
 // Session switch invalidates in-flight answer and login.
 state(2,true);run(10);handleKey(KEY_1_A);handleKey(KEY_OK);run(10);auto old=token();
 run(420,false);state(2,true,2);loop();assert(!loggedIn && pending.kind==PENDING_NONE);
 run(150,true,2,true,2);assert(pending.kind==PENDING_LOGIN);run(10,true,2,true,2);
 ack(old);assert(pending.kind==PENDING_LOGIN);ack(token());assert(loggedIn);
 state(2,false,2);run(32000,true,2,false,2);assert(idleSleeping && Bluefruit.Scanner.running);
 state(3,true,2);loop();assert(!idleSleeping && currentQuestion==3);
 // Loss of STATE is not permission to keep answering.
 run(16000,false);assert(!ArsBle::ready() && !loggedIn && currentQuestion==0);
 state(3,true,2);run(10,true,3,true,2);ack(token());assert(loggedIn);
 handleKey(KEY_1_A);handleKey(KEY_OK);run(20000,true,3,true,2);
 assert(pending.kind==PENDING_NONE && !fakeAdRunning); // bounded timeout
 // Entropy not ready: no weak/random fallback token transmitted.
 auto n=fakeAds.size();fakeRandFail=true;handleKey(KEY_1_A);handleKey(KEY_OK);run(100,true,3,true,2);
 assert(fakeAds.size()==n);fakeRandFail=false;run(3000,true,3,true,2);assert(fakeAds.size()>n);
 ack(token());assert(pending.kind==PENDING_NONE);
 // TX startup failure must immediately restore receive mode.
 fakeAdFail=true;handleKey(KEY_1_A);handleKey(KEY_OK);run(10,false);
 assert(!fakeAdRunning && Bluefruit.Scanner.running);
 ArsBle::finishTransaction();pending.kind=PENDING_NONE;fakeAdFail=false;
 // Stop failure does not accidentally run both radio roles.
 fakeScanStopFail=true;handleKey(KEY_1_A);handleKey(KEY_OK);run(10,false);
 assert(!fakeAdRunning && Bluefruit.Scanner.running);
 ArsBle::finishTransaction();pending.kind=PENDING_NONE;fakeScanStopFail=false;
 // Failed RX restart is retried without keeping advertising enabled.
 handleKey(KEY_1_A);handleKey(KEY_OK);run(10,false);assert(fakeAdRunning);
 fakeScanFail=true;run(420,false);assert(!fakeAdRunning && !Bluefruit.Scanner.running);
 fakeScanFail=false;run(260,false);assert(Bluefruit.Scanner.running);
 ArsBle::finishTransaction();pending.kind=PENDING_NONE;
 std::cout<<"ADV firmware PASS: fresh token/retry, wrong/stale ACK, room, session, bounded timeout, entropy failure, idle/wake, exclusive TX/RX, radio failure recovery.\n";
}
