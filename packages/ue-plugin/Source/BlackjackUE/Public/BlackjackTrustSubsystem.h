#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "BlackjackTrustSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackTrustChanged, int32, SeatIndex, float, NewTrust);

UCLASS()
class BLACKJACKUE_API UBlackjackTrustSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    /** 0.0..1.0 per NPC seat. Starts at 0.5 neutral. */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Trust")
    float GetTrust(int32 SeatIndex) const;

    UFUNCTION(BlueprintCallable, Category="Blackjack|Trust")
    void SetTrust(int32 SeatIndex, float NewTrust);

    UFUNCTION(BlueprintCallable, Category="Blackjack|Trust")
    void AdjustTrust(int32 SeatIndex, float Delta);

    /** Designer hook: when a player's bluff is "called" (NPC saw through
     *  it), that NPC's trust in the player drops by this amount. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Trust")
    float BluffCalledPenalty = 0.12f;

    /** Likewise when a bluff "works" -- NPCs who fell for it get a small
     *  trust bump because the player's "performance" registers as genuine. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Trust")
    float BluffBelievedBump = 0.04f;

    /** Convenience: call when a bluff result is observed. Applies
     *  BluffCalledPenalty/BluffBelievedBump uniformly across all seats
     *  OR to a specific seat if SeatIndex >= 0. */
    UFUNCTION(BlueprintCallable, Category="Blackjack|Trust")
    void ApplyBluffOutcome(bool bCalled, int32 SeatIndex = -1);

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Trust")
    FOnBlackjackTrustChanged OnTrustChanged;

    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    TMap<int32, float> Trust;  // seatIndex -> trust [0..1]
    float Clamp01(float V) const { return FMath::Clamp(V, 0.f, 1.f); }
};
