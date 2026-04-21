#include "BlackjackTrustSubsystem.h"

namespace
{
    constexpr float kNeutralTrust = 0.5f;
    constexpr int32 kDefaultSeatCount = 6;  // matches FBlackjackTableSummary::MaxSeats default
}

void UBlackjackTrustSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    // No timers; seats are created lazily via GetTrust/SetTrust.
}

void UBlackjackTrustSubsystem::Deinitialize()
{
    Trust.Empty();
    Super::Deinitialize();
}

float UBlackjackTrustSubsystem::GetTrust(int32 SeatIndex) const
{
    const float* Found = Trust.Find(SeatIndex);
    return Found ? *Found : kNeutralTrust;
}

void UBlackjackTrustSubsystem::SetTrust(int32 SeatIndex, float NewTrust)
{
    const float Clamped = Clamp01(NewTrust);
    Trust.Add(SeatIndex, Clamped);
    OnTrustChanged.Broadcast(SeatIndex, Clamped);
}

void UBlackjackTrustSubsystem::AdjustTrust(int32 SeatIndex, float Delta)
{
    SetTrust(SeatIndex, GetTrust(SeatIndex) + Delta);
}

void UBlackjackTrustSubsystem::ApplyBluffOutcome(bool bCalled, int32 SeatIndex)
{
    const float Delta = bCalled ? -BluffCalledPenalty : BluffBelievedBump;

    if (SeatIndex >= 0)
    {
        AdjustTrust(SeatIndex, Delta);
        return;
    }

    // Broadcast-mode: apply to every seat we know about, plus 0..kDefaultSeatCount-1
    // so fresh tables get initialized even before any SetTrust calls.
    TSet<int32> Seats;
    for (const TPair<int32, float>& Pair : Trust)
    {
        Seats.Add(Pair.Key);
    }
    for (int32 i = 0; i < kDefaultSeatCount; ++i)
    {
        Seats.Add(i);
    }
    for (int32 Seat : Seats)
    {
        AdjustTrust(Seat, Delta);
    }
}
