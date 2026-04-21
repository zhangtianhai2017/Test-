// Pure-C++ HUD for the Blackjack sample — draws raw text via Canvas.
// No UMG, no .uasset widgets. Validated for UE 5.6.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "BlackjackTypes.h"
#include "BlackjackNetClient.h"
#include "BlackjackSampleHUD.generated.h"

UCLASS()
class BLACKJACKSAMPLE_API ABlackjackSampleHUD : public AHUD
{
    GENERATED_BODY()

public:
    ABlackjackSampleHUD();

    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    virtual void DrawHUD() override;

protected:
    // Cached state collected from net-client events.
    UPROPERTY() EBlackjackConnectionState ConnectionState = EBlackjackConnectionState::Disconnected;
    UPROPERTY() EBlackjackPhase Phase = EBlackjackPhase::Betting;
    UPROPERTY() int32 ActiveSeatIndex = -1;
    UPROPERTY() int32 LocalBankroll = 0;
    UPROPERTY() FString LastDealerQuip;

    // Delegate handlers.
    UFUNCTION() void HandleConnectionStateChanged(EBlackjackConnectionState NewState);
    UFUNCTION() void HandlePhaseChanged(EBlackjackPhase NewPhase);
    UFUNCTION() void HandleBankrollChanged(int32 SeatIndex, int32 NewBalance, int32 Delta);
    UFUNCTION() void HandleTableState(const FBlackjackTableStateSnapshot& Snapshot);
    UFUNCTION() void HandleDealerQuip(const FString& Text, const FString& Tone, const FString& Language, const FString& AudioUrl);

private:
    UBlackjackNetClient* GetNetClient() const;
    static FString PhaseToString(EBlackjackPhase InPhase);
    static FString ConnStateToString(EBlackjackConnectionState InState);
};
