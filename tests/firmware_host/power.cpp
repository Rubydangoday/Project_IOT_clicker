// Real firmware, real keypad scanner/debouncer; virtual GPIO matrix and BLE.
#include <cassert>
#include <iostream>
#include <bluefruit.h>
#include "../../firmware/ARS_remote_v3_15/ARS_remote_v3_15.ino"

static void queue(std::initializer_list<uint8_t> bytes) {
 fakeRx.push_back((uint8_t)bytes.size());for(auto b:bytes)fakeRx.push_back(b);
}
static void heartbeat() {queue({0xA5,0x20,gRoom});}
static void snapshot(uint8_t q,bool open,uint8_t options=4) {
 queue({0xA5,0x10,gRoom,q,(uint8_t)open,options,0,0,0,0,0,0,0,0,0,0,0,0,0});
}
static void runFor(uint32_t ms,bool hello=true,bool duplicates=false) {
 uint32_t start=millis(),beat=start;
 while((uint32_t)(millis()-start)<ms) {
  if(hello && (uint32_t)(millis()-beat)>=1000) {
   heartbeat();if(duplicates)snapshot(0,false,0);beat=millis();
  }
  auto before=millis();loop();if(millis()==before)fakeMillis++;
 }
}
static void press(uint32_t row,uint32_t col) {
 fakeKeys={{row,col}};runFor(35);
}
static void release() {fakeKeys.clear();runFor(35);}
static bool displayBlank() {
 if(!gpioHigh[BoardPins::DIGIT_1] || !gpioHigh[BoardPins::DIGIT_2])return false;
 for(auto p:{BoardPins::SEG_A,BoardPins::SEG_B,BoardPins::SEG_C,BoardPins::SEG_D,
             BoardPins::SEG_E,BoardPins::SEG_F,BoardPins::SEG_G})if(!gpioHigh[p])return false;
 return true;
}
static void quietClosed() {
 snapshot(0,false,0);loop();runFor(31000,true,true);
 assert(idleSleeping && loggedIn && ArsBle::ready() && displayBlank());
 assert(!gpioOutput[BoardPins::STATUS_LED]);
}

int main() {
 fakeMillis=100;gRoom=1;gSeat=2;
 displayBegin();statusLedBegin();keypadBegin();ArsBle::begin(gRoom,gSeat);
 fakeConnected=fakeNotify=true;
 heartbeat();loop();assert(pending.kind==PENDING_LOGIN);
 queue({0xA5,0x14,gRoom,gSeat,pending.seq,0});loop();
 assert(loggedIn);

 // No STATE is not equivalent to no question, even after the idle timeout.
 runFor(35000);assert(!idleSleeping && !serverStateKnown);
 snapshot(0,false,0);loop();
 runFor(29000,true,true);assert(!idleSleeping);
 runFor(1100,true,true);assert(idleSleeping && displayBlank());
 auto idleStart=millis();loop();assert(millis()-idleStart==IDLE_POLL_MS);
 runFor(60000,true,true);assert(idleSleeping && ArsBle::ready() && displayBlank());

 // Open STATE wakes without reconnect/login, and no duplicate answer is sent.
 auto loginSeq=seqNo;
 snapshot(2,true);loop();
 assert(!idleSleeping && questionAnswerable() && currentQuestion==2);
 assert(loggedIn && pending.kind==PENDING_NONE && seqNo==loginSeq && !displayBlank());
 runFor(35000);assert(!idleSleeping); // an open question always prevents idle
 quietClosed();

 // First raw MODE wakes; its eventual debounced event must also be consumed.
 press(BoardPins::ROW_3,BoardPins::COL_4);
 assert(!idleSleeping && uiMode==UI_NORMAL && suppressKeysUntilRelease);
 runFor(35000);assert(!idleSleeping && uiMode==UI_NORMAL); // held key
 release();assert(!suppressKeysUntilRelease);
 press(BoardPins::ROW_3,BoardPins::COL_4);release();
 assert(uiMode==UI_ENTER_SEAT);
 runFor(35000);assert(!idleSleeping);
 press(BoardPins::ROW_3,BoardPins::COL_4);release();
 assert(uiMode==UI_ENTER_ROOM);runFor(35000);assert(!idleSleeping);
 press(BoardPins::ROW_1,BoardPins::COL_4);release();assert(uiMode==UI_NORMAL);
 quietClosed();

 // A short bounce wakes but cannot become an action when the key settles.
 fakeKeys={{BoardPins::ROW_1,BoardPins::COL_1}};loop();
 assert(!idleSleeping && suppressKeysUntilRelease && selectedAnswer==0);
 fakeKeys.clear();runFor(3);
 fakeKeys={{BoardPins::ROW_1,BoardPins::COL_1}};runFor(35);
 assert(selectedAnswer==0);release();
 quietClosed();

 // Simultaneous question arrival and OK press: waking cannot submit anything.
 snapshot(4,true);fakeKeys={{BoardPins::ROW_4,BoardPins::COL_3}};loop();
 runFor(35);assert(!idleSleeping && pending.kind==PENDING_NONE && selectedAnswer==0);
 release();press(BoardPins::ROW_1,BoardPins::COL_2);release();assert(selectedAnswer==2);
 press(BoardPins::ROW_4,BoardPins::COL_3);release();assert(pending.kind==PENDING_ANSWER);
 auto transaction=pending;
 snapshot(4,false);loop();assert(!idleSleeping && pending.kind==PENDING_ANSWER);
 runFor(1200);assert(!idleSleeping && pending.kind==PENDING_ANSWER);
 assert(pending.question==transaction.question && pending.seq==transaction.seq && pending.answer==2);
 queue({0xA5,0x13,gRoom,1,gSeat,transaction.question,transaction.seq,2,0});loop();
 assert(pending.kind==PENDING_NONE && !idleSleeping);
 runFor(350);assert(!idleSleeping); // preserve success flash
 quietClosed();

 // Lost heartbeat must wake and clear state even if radio still connected.
 runFor(9000,false);assert(!idleSleeping && !loggedIn && !serverStateKnown);
 assert(fakeConnected && !ArsBle::ready());
 heartbeat();loop();assert(pending.kind==PENDING_LOGIN && !idleSleeping);
 // Stalled LOGIN times out visibly, never goes idle without successful login.
 runFor(35000);assert(!idleSleeping && !loggedIn && pending.kind==PENDING_NONE);
 beginLogin();queue({0xA5,0x14,gRoom,gSeat,pending.seq,0});loop();quietClosed();

 // Actual disconnection wakes, reconnect requires a fresh STATE and LOGIN.
 fakeConnected=false;Bluefruit.Periph.disconnect(0,0);loop();
 assert(!idleSleeping && !serverStateKnown && !loggedIn);
 fakeConnected=true;heartbeat();loop();
 queue({0xA5,0x14,gRoom,gSeat,pending.seq,0});loop();runFor(35000);
 assert(!idleSleeping && !serverStateKnown);
 snapshot(100,true);loop();runFor(35000);assert(!idleSleeping);
 snapshot(1,true,0);loop();runFor(35000);assert(!idleSleeping); // invalid open != closed
 quietClosed();

 // Multiple keys wake once, no edit/answer action, release is still required.
 fakeKeys={{BoardPins::ROW_1,BoardPins::COL_1},{BoardPins::ROW_4,BoardPins::COL_3}};
 runFor(35);assert(!idleSleeping && suppressKeysUntilRelease && pending.kind==PENDING_NONE);
 release();assert(!suppressKeysUntilRelease);

 // Real key activity restarts a full 30-second quiet interval.
 runFor(20000);press(BoardPins::ROW_1,BoardPins::COL_4);release();
 runFor(29000);assert(!idleSleeping);runFor(1100);assert(idleSleeping);

 // Timeout arithmetic survives millis wrap; heartbeat refreshed after jump.
 press(BoardPins::ROW_1,BoardPins::COL_4);release();
 fakeMillis=0xfffffff0u;heartbeat();
 statusLedSet(STATUS_OFF);errorUntilMs=0;lastActivityMs=millis();loop();
 runFor(29000,true,true);assert(!idleSleeping);
 runFor(1100,true,true);assert(idleSleeping && ArsBle::ready());
 std::cout<<"Power scenarios passed: real keypad debounce, idle thresholds, heartbeat, duplicate STATE, held/multiple keys, wake suppression, question wake, ACK/retry, edits, disconnect, millis wrap.\n";
}
