#include "BlackjackMoraleSubsystem.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "TimerManager.h"

namespace
{
    constexpr float kMoraleNeutral = 0.5f;
}

void UBlackjackMoraleSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    Morale = 0.75f;

    if (UGameInstance* GI = GetGameInstance())
    {
        if (UWorld* World = GI->GetWorld())
        {
            World->GetTimerManager().SetTimer(
                RegressTimer,
                FTimerDelegate::CreateUObject(this, &UBlackjackMoraleSubsystem::TickRegression),
                1.0f,
                /*bLoop=*/true);
        }
    }
}

void UBlackjackMoraleSubsystem::Deinitialize()
{
    if (UGameInstance* GI = GetGameInstance())
    {
        if (UWorld* World = GI->GetWorld())
        {
            World->GetTimerManager().ClearTimer(RegressTimer);
        }
    }
    RegressTimer.Invalidate();

    Super::Deinitialize();
}

void UBlackjackMoraleSubsystem::SetMorale(float NewMorale)
{
    const float Clamped = FMath::Clamp(NewMorale, 0.0f, 1.0f);
    const float Old = Morale;
    if (FMath::IsNearlyEqual(Clamped, Old))
    {
        return;
    }

    Morale = Clamped;
    OnMoraleChanged.Broadcast(Morale, Morale - Old);
}

void UBlackjackMoraleSubsystem::AdjustMorale(float Delta)
{
    SetMorale(Morale + Delta);
}

void UBlackjackMoraleSubsystem::TickRegression()
{
    if (RegressionPerSecond <= 0.f)
    {
        return;
    }
    if (FMath::IsNearlyEqual(Morale, kMoraleNeutral, 1e-4f))
    {
        return;
    }

    // Move toward neutral by RegressionPerSecond * 1.0s, bounded so we never
    // overshoot across the neutral line.
    const float Step = RegressionPerSecond;
    if (Morale > kMoraleNeutral)
    {
        SetMorale(FMath::Max(kMoraleNeutral, Morale - Step));
    }
    else
    {
        SetMorale(FMath::Min(kMoraleNeutral, Morale + Step));
    }
}
