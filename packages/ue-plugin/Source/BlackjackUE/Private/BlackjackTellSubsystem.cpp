#include "BlackjackTellSubsystem.h"

void UBlackjackTellSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    // No timers, no further setup. Wiring to NetClient.OnGestureMade is
    // performed externally via UBlackjackPerceptionWiring::InstallPerceptionWiring
    // so designers can pick when/whether to install it.
}

void UBlackjackTellSubsystem::Deinitialize()
{
    Counts.Empty();
    Spotted.Empty();
    Super::Deinitialize();
}

FString UBlackjackTellSubsystem::KeyOf(int32 Seat, EBlackjackGesture G)
{
    return FString::Printf(TEXT("%d:%d"), Seat, (uint8)G);
}

void UBlackjackTellSubsystem::ObserveGesture(int32 SeatIndex, EBlackjackGesture Gesture)
{
    const FString Key = KeyOf(SeatIndex, Gesture);
    int32& Count = Counts.FindOrAdd(Key);
    ++Count;

    if (Count >= SpottedThreshold && !Spotted.Contains(Key))
    {
        Spotted.Add(Key);
        OnTellSpotted.Broadcast(SeatIndex, Gesture);
    }
}

bool UBlackjackTellSubsystem::IsSpotted(int32 SeatIndex, EBlackjackGesture Gesture) const
{
    return Spotted.Contains(KeyOf(SeatIndex, Gesture));
}

int32 UBlackjackTellSubsystem::GetObservationCount(int32 SeatIndex, EBlackjackGesture Gesture) const
{
    const int32* Found = Counts.Find(KeyOf(SeatIndex, Gesture));
    return Found ? *Found : 0;
}

void UBlackjackTellSubsystem::ResetSeat(int32 SeatIndex)
{
    const FString Prefix = FString::Printf(TEXT("%d:"), SeatIndex);

    // Collect-then-remove to avoid invalidating the iterator on the TMap.
    TArray<FString> ToRemoveCounts;
    for (const TPair<FString, int32>& Pair : Counts)
    {
        if (Pair.Key.StartsWith(Prefix))
        {
            ToRemoveCounts.Add(Pair.Key);
        }
    }
    for (const FString& Key : ToRemoveCounts)
    {
        Counts.Remove(Key);
    }

    TArray<FString> ToRemoveSpotted;
    for (const FString& Key : Spotted)
    {
        if (Key.StartsWith(Prefix))
        {
            ToRemoveSpotted.Add(Key);
        }
    }
    for (const FString& Key : ToRemoveSpotted)
    {
        Spotted.Remove(Key);
    }
}

void UBlackjackTellSubsystem::HandleGestureMade(int32 SeatIndex, EBlackjackGesture Gesture)
{
    ObserveGesture(SeatIndex, Gesture);
}
