#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "BlackjackNetClient.h"  // for EBlackjackGesture
#include "BlackjackTellSubsystem.generated.h"

/**
 * An NPC "tell" is a repeatable correlation between a trigger (a gesture
 * they make) and an outcome. Players learn tells by observing -- after
 * seeing the same (seat, gesture) -> outcome pattern K times, the player
 * "spots" that tell and it's visualized (pulse / gleam) the next time
 * the NPC does it.
 *
 * This subsystem stores:
 *   observations[seatIndex][gesture]  -> count
 *   spottedTells[seatIndex]           -> Set<gesture>
 *
 * Game-server / designer hooks feed observations via ObserveGesture();
 * threshold for "spotted" is 3 by default.
 */

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackTellSpotted, int32, SeatIndex, EBlackjackGesture, Gesture);

UCLASS()
class BLACKJACKUE_API UBlackjackTellSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Blackjack|Tell")
    void ObserveGesture(int32 SeatIndex, EBlackjackGesture Gesture);

    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Tell")
    bool IsSpotted(int32 SeatIndex, EBlackjackGesture Gesture) const;

    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Tell")
    int32 GetObservationCount(int32 SeatIndex, EBlackjackGesture Gesture) const;

    UFUNCTION(BlueprintCallable, Category="Blackjack|Tell")
    void ResetSeat(int32 SeatIndex);

    /**
     * Forwarding UFUNCTION handler so the NetClient's OnGestureMade
     * dynamic delegate can bind directly via AddDynamic() without a
     * helper UObject. Simply forwards to ObserveGesture.
     */
    UFUNCTION()
    void HandleGestureMade(int32 SeatIndex, EBlackjackGesture Gesture);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Tell")
    int32 SpottedThreshold = 3;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Tell")
    FOnBlackjackTellSpotted OnTellSpotted;

    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    // Keyed strings "seatIndex:gesture" -> int32 count (using TMap because
    // nested TMaps for U-types are awkward in UE reflection).
    TMap<FString, int32> Counts;
    TSet<FString> Spotted;
    static FString KeyOf(int32 Seat, EBlackjackGesture G);
};
