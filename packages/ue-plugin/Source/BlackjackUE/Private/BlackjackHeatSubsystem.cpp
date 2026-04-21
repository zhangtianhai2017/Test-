#include "BlackjackHeatSubsystem.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "TimerManager.h"

void UBlackjackHeatSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    Heat = 0;
    CrossThresholds = { 30, 60, 90 };

    // Start the 1s decay timer. World may not be ready synchronously during
    // subsystem init; guard and fall back to the game-instance's world lookup.
    if (UGameInstance* GI = GetGameInstance())
    {
        if (UWorld* World = GI->GetWorld())
        {
            World->GetTimerManager().SetTimer(
                DecayTimer,
                FTimerDelegate::CreateUObject(this, &UBlackjackHeatSubsystem::TickDecay),
                1.0f,
                /*bLoop=*/true);
        }
    }
}

void UBlackjackHeatSubsystem::Deinitialize()
{
    if (UGameInstance* GI = GetGameInstance())
    {
        if (UWorld* World = GI->GetWorld())
        {
            World->GetTimerManager().ClearTimer(DecayTimer);
        }
    }
    DecayTimer.Invalidate();

    Super::Deinitialize();
}

void UBlackjackHeatSubsystem::SetHeat(int32 NewHeat)
{
    const int32 Clamped = FMath::Clamp(NewHeat, 0, 100);
    const int32 Old = Heat;
    if (Clamped == Old)
    {
        return;
    }

    Heat = Clamped;
    OnHeatChanged.Broadcast(Heat, Heat - Old);
    FireCrossings(Old, Heat);
}

void UBlackjackHeatSubsystem::AdjustHeat(int32 Delta)
{
    SetHeat(Heat + Delta);
}

void UBlackjackHeatSubsystem::TickDecay()
{
    if (Heat <= 0)
    {
        return;
    }
    // Integer decay step: floor of DecayPerSecond, minimum 1 when positive so
    // designers setting DecayPerSecond in (0,1) still observe decay.
    int32 Step = FMath::FloorToInt(DecayPerSecond);
    if (Step <= 0 && DecayPerSecond > 0.f)
    {
        Step = 1;
    }
    if (Step <= 0)
    {
        return;
    }
    AdjustHeat(-Step);
}

void UBlackjackHeatSubsystem::FireCrossings(int32 Old, int32 New)
{
    // Design choice: only fire on upward crossings (Old < t <= New). The
    // pit-boss / UI flows react to *escalation*; cool-down visuals are driven
    // by the (Delta < 0) arg on OnHeatChanged. The reverse-direction case
    // (Old >= t > New) is intentionally ignored per M7a spec.
    if (New <= Old)
    {
        return;
    }
    for (const int32 T : CrossThresholds)
    {
        if (Old < T && T <= New)
        {
            OnThresholdCrossed.Broadcast(T);
        }
    }
}
