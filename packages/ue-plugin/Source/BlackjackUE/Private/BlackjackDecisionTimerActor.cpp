#include "BlackjackDecisionTimerActor.h"
#include "Engine/World.h"
#include "TimerManager.h"

ABlackjackDecisionTimerActor::ABlackjackDecisionTimerActor()
{
    PrimaryActorTick.bCanEverTick = false;
}

void ABlackjackDecisionTimerActor::BeginPlay()
{
    Super::BeginPlay();
}

void ABlackjackDecisionTimerActor::EndPlay(const EEndPlayReason::Type Reason)
{
    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().ClearTimer(TickHandle);
    }
    bRunning = false;
    Super::EndPlay(Reason);
}

void ABlackjackDecisionTimerActor::StartTimer(float DurationSeconds)
{
    RemainingSeconds = DurationSeconds > 0.f ? DurationSeconds : DefaultDurationSeconds;
    bRunning = true;

    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().ClearTimer(TickHandle);
        World->GetTimerManager().SetTimer(
            TickHandle,
            this,
            &ABlackjackDecisionTimerActor::TickImpl,
            0.1f,
            true);
    }

    OnTimerStart.Broadcast(RemainingSeconds);
}

void ABlackjackDecisionTimerActor::CancelTimer()
{
    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().ClearTimer(TickHandle);
    }
    bRunning = false;
    OnTimerCancel.Broadcast();
}

void ABlackjackDecisionTimerActor::TickImpl()
{
    RemainingSeconds -= 0.1f;
    if (RemainingSeconds <= 0.f)
    {
        RemainingSeconds = 0.f;
        if (UWorld* World = GetWorld())
        {
            World->GetTimerManager().ClearTimer(TickHandle);
        }
        bRunning = false;
        OnTimerExpire.Broadcast();
    }
    else
    {
        OnTimerTick.Broadcast(RemainingSeconds);
    }
}
