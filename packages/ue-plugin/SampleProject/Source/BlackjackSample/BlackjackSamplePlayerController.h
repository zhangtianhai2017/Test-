// Pure-C++ PlayerController for the Blackjack SampleProject.
//
// All EnhancedInput wiring is created at runtime via NewObject<> — no
// .uasset IMC / IA assets are shipped or required. Keybindings are the
// hardcoded defaults listed in the class comment below and can be
// overridden in a child class by replacing the bindings in
// BuildInputMappings().
//
// Validated against UE 5.6.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "BlackjackNetClient.h" // EBlackjackGesture + subsystem API
#include "BlackjackSamplePlayerController.generated.h"

class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/**
 * Default keybindings (set in BuildInputMappings, overridable in a child):
 *   1 / 2 / 3 = Bet 5 / 25 / 100
 *   H = Hit      S = Stand   D = Double   P = Split   R = Surrender
 *   N = NewRound
 *   C = Confident   X = Nervous   O = PokerFace
 *   T = Taunt       G = Sigh      V = Celebrate
 */
UCLASS()
class BLACKJACKSAMPLE_API ABlackjackSamplePlayerController : public APlayerController
{
    GENERATED_BODY()

public:
    ABlackjackSamplePlayerController();

    /** Seat index this controller has claimed (-1 until SEAT_ASSIGNED fires for us). */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack")
    int32 ClaimedSeatIndex = -1;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void SetupInputComponent() override;

    // Action handlers --------------------------------------------------------
    void HandleBet5(const FInputActionValue&)    { PlaceQuickBet(5); }
    void HandleBet25(const FInputActionValue&)   { PlaceQuickBet(25); }
    void HandleBet100(const FInputActionValue&)  { PlaceQuickBet(100); }
    void HandleHit(const FInputActionValue&);
    void HandleStand(const FInputActionValue&);
    void HandleDouble(const FInputActionValue&);
    void HandleSplit(const FInputActionValue&);
    void HandleSurrender(const FInputActionValue&);
    void HandleNewRound(const FInputActionValue&);

    void HandleGestureConfident(const FInputActionValue&)  { SendGesture(EBlackjackGesture::Confident); }
    void HandleGestureNervous(const FInputActionValue&)    { SendGesture(EBlackjackGesture::Nervous); }
    void HandleGesturePokerFace(const FInputActionValue&)  { SendGesture(EBlackjackGesture::PokerFace); }
    void HandleGestureTaunt(const FInputActionValue&)      { SendGesture(EBlackjackGesture::Taunt); }
    void HandleGestureSigh(const FInputActionValue&)       { SendGesture(EBlackjackGesture::Sigh); }
    void HandleGestureCelebrate(const FInputActionValue&)  { SendGesture(EBlackjackGesture::Celebrate); }

    // Net-client bookkeeping.
    UFUNCTION() void HandleSeatAssigned(int32 SeatIndex, const FString& OwnerClientId);
    UFUNCTION() void HandleSeatReleased(int32 SeatIndex, bool bBecameNpc, const FString& Personality);

    // Helpers ----------------------------------------------------------------
    UBlackjackNetClient* GetNetClient() const;
    void PlaceQuickBet(int32 Amount);
    void SendGesture(EBlackjackGesture Gesture);

    // Runtime-constructed EnhancedInput assets. Not UPROPERTY so GC doesn't
    // collect them while we hold the IMC — we pin them by adding to root.
    UPROPERTY() UInputMappingContext* InputMapping = nullptr;

    UPROPERTY() UInputAction* IA_Bet5 = nullptr;
    UPROPERTY() UInputAction* IA_Bet25 = nullptr;
    UPROPERTY() UInputAction* IA_Bet100 = nullptr;
    UPROPERTY() UInputAction* IA_Hit = nullptr;
    UPROPERTY() UInputAction* IA_Stand = nullptr;
    UPROPERTY() UInputAction* IA_Double = nullptr;
    UPROPERTY() UInputAction* IA_Split = nullptr;
    UPROPERTY() UInputAction* IA_Surrender = nullptr;
    UPROPERTY() UInputAction* IA_NewRound = nullptr;
    UPROPERTY() UInputAction* IA_GestureConfident = nullptr;
    UPROPERTY() UInputAction* IA_GestureNervous = nullptr;
    UPROPERTY() UInputAction* IA_GesturePokerFace = nullptr;
    UPROPERTY() UInputAction* IA_GestureTaunt = nullptr;
    UPROPERTY() UInputAction* IA_GestureSigh = nullptr;
    UPROPERTY() UInputAction* IA_GestureCelebrate = nullptr;

private:
    /** Build the IMC + 15 IAs at runtime. Overridable by calling from a child. */
    void BuildInputMappings();
    /** Push the IMC onto the local player's EnhancedInput subsystem. */
    void ActivateInputMapping();
};
