// Pure-C++ GameMode for the Blackjack sample — spawns the entire scene in
// BeginPlay so the sample needs no Blueprint .uasset placements. Validated for UE 5.6.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "BlackjackSampleGameMode.generated.h"

class ABlackjackNetTableActor;
class ABlackjackDealerCharacter;
class ABlackjackPitBossActor;
class ABlackjackDecisionTimerActor;
class ABlackjackChipStackActor;

/**
 * Spawns the net table, dealer, pit boss, decision timer, and 6 seat chip
 * stacks arranged in a hex around the felt. Also resolves the
 * UBlackjackNetClient subsystem and Connect()s it using CLI args
 * (`-bjhost=... -bjport=... -bjname=...`), falling back to 127.0.0.1:7878 and
 * "TestPlayer".
 *
 * DefaultPawnClass / PlayerControllerClass / HUDClass are set in the
 * constructor to the pure-C++ sample classes — no BP subclassing needed.
 */
UCLASS()
class BLACKJACKSAMPLE_API ABlackjackSampleGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    ABlackjackSampleGameMode();

protected:
    virtual void BeginPlay() override;

    /** Spawned scene actors — kept as UPROPERTY so GC keeps them live. */
    UPROPERTY() ABlackjackNetTableActor* NetTable = nullptr;
    UPROPERTY() ABlackjackDealerCharacter* DealerChar = nullptr;
    UPROPERTY() ABlackjackPitBossActor* PitBoss = nullptr;
    UPROPERTY() ABlackjackDecisionTimerActor* DecisionTimer = nullptr;
    UPROPERTY() TArray<ABlackjackChipStackActor*> SeatChipStacks;

private:
    /** Compute the 6-seat hex layout and the dealer bet transform. */
    static void BuildSeatLayout(TArray<FTransform>& OutSeats, FTransform& OutDealer);

    /** Parse -bjhost=... -bjport=... -bjname=... from FCommandLine::Get(). */
    static void ParseConnectArgs(FString& OutHost, int32& OutPort, FString& OutName);
};
