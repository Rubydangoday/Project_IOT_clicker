// Test the real application/radio/display code using host-only hardware mocks.
#include <cassert>
#include <iostream>
#include <bluefruit.h>
#include "../../firmware/ARS_remote_v3_15/ARS_remote_v3_15.ino"
static void rx(std::initializer_list<uint8_t> data) {
 fakeRx.push_back((uint8_t)data.size());for(auto b:data)fakeRx.push_back(b);ArsBle::update();
}
static void state(uint8_t q,bool open,uint8_t options=4) {
 rx({0xA5,0x10,gRoom,q,(uint8_t)open,options,0,0,0,0,0,0,0,0,0,0,0,0,0});
 processDownlink();
}
static std::pair<uint8_t,uint8_t> segments() {
 uint8_t left=0,right=0;
 const uint32_t pins[]={BoardPins::SEG_A,BoardPins::SEG_B,BoardPins::SEG_C,BoardPins::SEG_D,BoardPins::SEG_E,BoardPins::SEG_F,BoardPins::SEG_G};
 for(int digit=0;digit<2;digit++) {
  fakeMillis+=2;displayUpdate();uint8_t bits=0;
  for(int j=0;j<7;j++)if(!gpioHigh[pins[j]])bits|=1u<<j;
  if(!gpioHigh[BoardPins::DIGIT_1])left=bits;else right=bits;
 }
 return {left,right};
}
int main() {
 fakeMillis=100;
 displayBegin();statusLedBegin();keypadBegin();gRoom=1;gSeat=2;
 ArsBle::begin(gRoom,gSeat);beginLogin();
 assert(pending.kind==PENDING_NONE && loginWanted && fakeTx.empty());
 fakeConnected=fakeNotify=true;
 rx({0xA5,0x22,1,2,3,4}); // probe must NOT authorize real LOGIN
 assert(fakeTx.back()==std::vector<uint8_t>({6,0xA5,0x23,1,2,3,4}));
 assert(!ArsBle::ready());
 rx({0xA5,0x20,0}); // V3.12 discovery: reply with saved Room, do not authorize login
 assert(!ArsBle::ready());
 assert(fakeTx.back()==std::vector<uint8_t>({4,0xA5,0x21,1,2}));
 rx({0xA5,0x20,1});processConnection();
 assert(ArsBle::ready() && pending.kind==PENDING_LOGIN);
 uint8_t loginSequence=pending.seq;
 rx({0xA5,0x11,1,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff});
 processDownlink();assert(!loggedIn); // stale attendance bitmap is not a login ACK
 rx({0xA5,0x14,1,2,(uint8_t)(loginSequence+1),0});processDownlink();assert(!loggedIn);
 rx({0xA5,0x14,1,2,loginSequence,0});processDownlink();assert(loggedIn && pending.kind==PENDING_NONE);
 // Logged in without STATE: no answer packet, and a steady -- display.
 auto before=fakeTx.size();handleKey(KEY_1_A);handleKey(KEY_OK);renderUi();
 assert(selectedAnswer==0 && pending.kind==PENDING_NONE && fakeTx.size()==before);
 auto sync=segments();assert(sync.first==0x40 && sync.second==0x40);
 rx({0xA5,0x10,1,1,1,4,0,0,0,0,0,0,0,0,0,0,0,0,0});processDownlink();
 assert(currentQuestion==1 && questionAnswerable());
 selectedAnswer=3;beginAnswer();uint8_t answerSequence=pending.seq;
 assert(pending.kind==PENDING_ANSWER);
 rx({0xA5,0x13,1,1,2,1,answerSequence,2,0});processDownlink();assert(pending.kind==PENDING_ANSWER);
 // Backend not responding: retry exactly the same sequence and answer.
 fakeMillis=pending.deadlineMs;processRetry();fakeMillis=retryBackoffUntilMs;processRetry();
 assert(pending.seq==answerSequence && pending.answer==3 && pending.attempts==2);
 rx({0xA5,0x13,1,1,2,1,answerSequence,3,0});processDownlink();assert(pending.kind==PENDING_NONE && selectedAnswer==0);
 // Question selection follows STATE. Duplicate snapshots must keep an unsent choice.
 handleKey(KEY_1_A);state(1,true);assert(selectedAnswer==1);
 handleKey(KEY_LEFT);handleKey(KEY_RIGHT);assert(currentQuestion==1 && selectedAnswer==1);
 state(7,true);assert(currentQuestion==7 && selectedAnswer==0);
 handleKey(KEY_2_B);assert(selectedAnswer==2);
 state(7,false);renderUi();auto closed=segments();
 assert(selectedAnswer==0 && !questionAnswerable() && closed.first==0x39 && closed.second==0x38);
 before=fakeTx.size();handleKey(KEY_1_A);handleKey(KEY_OK);
 assert(fakeTx.size()==before && pending.kind==PENDING_NONE && selectedAnswer==0);
 state(7,true);handleKey(KEY_2_B);state(7,true,1);assert(selectedAnswer==0);
 handleKey(KEY_2_B);assert(selectedAnswer==0); // option B unavailable
 handleKey(KEY_1_A);handleKey(KEY_OK);assert(pending.kind==PENDING_ANSWER && pending.question==7);
 auto inFlight=pending;state(8,true);assert(currentQuestion==8 && selectedAnswer==0);
 handleKey(KEY_2_B);assert(selectedAnswer==0); // wait for the old exact result
 fakeMillis=pending.deadlineMs;processRetry();fakeMillis=retryBackoffUntilMs;processRetry();
 assert(pending.question==7 && pending.seq==inFlight.seq && pending.answer==1);
 assert(fakeTx.back()[5]==7 && fakeTx.back()[6]==inFlight.seq && fakeTx.back()[7]==1);
 rx({0xA5,0x13,1,1,2,8,inFlight.seq,1,0});processDownlink();assert(pending.kind==PENDING_ANSWER);
 rx({0xA5,0x13,1,1,2,7,inFlight.seq,1,0});processDownlink();
 assert(pending.kind==PENDING_NONE && currentQuestion==8 && selectedAnswer==0);
 handleKey(KEY_2_B);handleKey(KEY_OK);assert(pending.question==8 && pending.answer==2);
 // Close racing with an answer: matching NACK stops retries; closed display remains.
 state(8,false);rx({0xA5,0x13,1,1,2,8,pending.seq,2,2});processDownlink();
 assert(pending.kind==PENDING_NONE && !questionAnswerable());
 state(0,false);assert(currentQuestion==0 && !questionAnswerable());
 state(100,true);assert(currentQuestion==0 && !questionAnswerable());
 state(1,true,0);assert(!questionAnswerable());state(1,true);
 // Loss during answer must never automatically replay it after reconnection.
 selectedAnswer=2;beginAnswer();fakeConnected=false;Bluefruit.Periph.disconnect(0,0);ArsBle::update();processConnection();
 assert(pending.kind==PENDING_NONE && !loggedIn && selectedAnswer==0 && currentQuestion==0 && !serverQuestionOpen);
 fakeConnected=true;rx({0xA5,0x20,1});processConnection();assert(pending.kind==PENDING_LOGIN);
 // Modes have physically different segment patterns, even for the same value.
 displaySetMode(DISP_ROOM,2);auto room=segments();
 displaySetMode(DISP_SEAT,2);auto seat=segments();
 displaySetMode(DISP_QUESTION,2);auto question=segments();
 displaySetMode(DISP_ANSWER,2);auto answer=segments();
 assert(room!=seat && room!=question && room!=answer && seat!=question && seat!=answer && question!=answer);
 // Selected answer remains a letter across the old numeric/label phase boundary.
 fakeMillis+=450;assert(segments()==answer);
 displaySetMode(DISP_QUESTION,2,true);auto numeric=segments();assert(numeric.first==0x3f && numeric.second==0x5b);
 // Editing remains visible while Bluetooth is disconnected.
 fakeConnected=false;uiMode=UI_ENTER_ROOM;entryValue=1;renderUi();auto edit=segments();assert(edit.first==0x50);
 // HELLO heartbeat expires; a connected radio alone is not application-ready.
 fakeConnected=true;fakeMillis+=9000;assert(!ArsBle::ready());
 // V3.12 adoption uses unchanged firmware: room mismatch suspends app only.
 gRoom=4;ArsBle::setIdentity(4,2);uiMode=UI_NORMAL;processConnection();
 rx({0xA5,0x20,1});processConnection();assert(!ArsBle::ready() && fakeConnected);
 assert(fakeTx.back()==std::vector<uint8_t>({4,0xA5,0x21,4,2}));
 rx({0xA5,0x20,4});processConnection();assert(ArsBle::ready() && fakeConnected);
 assert(pending.kind==PENDING_LOGIN);
 rx({0xA5,0x14,4,2,pending.seq,0});processDownlink();state(3,true);handleKey(KEY_1_A);
 handleKey(KEY_MODE);assert(uiMode==UI_ENTER_SEAT && selectedAnswer==0);
 handleKey(KEY_LEFT);assert(uiMode==UI_NORMAL && currentQuestion==3); // LEFT still cancels entry
 handleKey(KEY_MODE);handleKey(KEY_MODE);handleKey(KEY_1_A);handleKey(KEY_OK);
 assert(gRoom==1 && currentQuestion==0 && !questionAnswerable() && uiMode==UI_ENTER_SEAT);
 std::cout<<"Firmware host scenarios passed: baseline GATT, auto question, closed/missing STATE, options, immutable in-flight ACK/retry, room reset, mode segments.\n";
}
