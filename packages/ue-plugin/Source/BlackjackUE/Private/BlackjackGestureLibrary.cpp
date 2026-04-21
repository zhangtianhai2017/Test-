#include "BlackjackGestureLibrary.h"
#include "Engine/World.h"
#include "Engine/GameInstance.h"

FText UBlackjackGestureLibrary::GestureDisplayName(EBlackjackGesture Gesture, const FString& Language)
{
    const bool bChinese = Language.Equals(TEXT("zh"), ESearchCase::IgnoreCase);
    if (bChinese)
    {
        switch (Gesture)
        {
            case EBlackjackGesture::Confident: return FText::FromString(TEXT("自信"));
            case EBlackjackGesture::Nervous:   return FText::FromString(TEXT("紧张"));
            case EBlackjackGesture::PokerFace: return FText::FromString(TEXT("面无表情"));
            case EBlackjackGesture::Taunt:     return FText::FromString(TEXT("挑衅"));
            case EBlackjackGesture::Sigh:      return FText::FromString(TEXT("叹气"));
            case EBlackjackGesture::Celebrate: return FText::FromString(TEXT("庆祝"));
        }
        return FText::FromString(TEXT(""));
    }

    switch (Gesture)
    {
        case EBlackjackGesture::Confident: return FText::FromString(TEXT("Confident"));
        case EBlackjackGesture::Nervous:   return FText::FromString(TEXT("Nervous"));
        case EBlackjackGesture::PokerFace: return FText::FromString(TEXT("Poker Face"));
        case EBlackjackGesture::Taunt:     return FText::FromString(TEXT("Taunt"));
        case EBlackjackGesture::Sigh:      return FText::FromString(TEXT("Sigh"));
        case EBlackjackGesture::Celebrate: return FText::FromString(TEXT("Celebrate"));
    }
    return FText::FromString(TEXT(""));
}

FString UBlackjackGestureLibrary::GestureShortLabel(EBlackjackGesture Gesture)
{
    switch (Gesture)
    {
        case EBlackjackGesture::Confident: return TEXT("C");
        case EBlackjackGesture::Nervous:   return TEXT("N");
        case EBlackjackGesture::PokerFace: return TEXT("P");
        case EBlackjackGesture::Taunt:     return TEXT("T");
        case EBlackjackGesture::Sigh:      return TEXT("S");
        case EBlackjackGesture::Celebrate: return TEXT("H");
    }
    return TEXT("?");
}

TArray<EBlackjackGesture> UBlackjackGestureLibrary::AllGestures()
{
    return {
        EBlackjackGesture::Confident,
        EBlackjackGesture::Nervous,
        EBlackjackGesture::PokerFace,
        EBlackjackGesture::Taunt,
        EBlackjackGesture::Sigh,
        EBlackjackGesture::Celebrate,
    };
}

bool UBlackjackGestureLibrary::GestureFromKey(const FString& Key, EBlackjackGesture& OutGesture)
{
    const FString K = Key.TrimStartAndEnd().ToLower();
    if (K.IsEmpty())
    {
        return false;
    }

    if (K == TEXT("c") || K == TEXT("confident"))
    {
        OutGesture = EBlackjackGesture::Confident;
        return true;
    }
    if (K == TEXT("n") || K == TEXT("nervous"))
    {
        OutGesture = EBlackjackGesture::Nervous;
        return true;
    }
    if (K == TEXT("p") || K == TEXT("poker") || K == TEXT("pokerface") || K == TEXT("poker face"))
    {
        OutGesture = EBlackjackGesture::PokerFace;
        return true;
    }
    if (K == TEXT("t") || K == TEXT("taunt"))
    {
        OutGesture = EBlackjackGesture::Taunt;
        return true;
    }
    if (K == TEXT("s") || K == TEXT("sigh"))
    {
        OutGesture = EBlackjackGesture::Sigh;
        return true;
    }
    if (K == TEXT("h") || K == TEXT("celebrate"))
    {
        OutGesture = EBlackjackGesture::Celebrate;
        return true;
    }
    return false;
}

void UBlackjackGestureLibrary::SendGesture(UObject* WorldContextObject, int32 SeatIndex, EBlackjackGesture Gesture)
{
    if (!WorldContextObject)
    {
        return;
    }
    UWorld* World = WorldContextObject->GetWorld();
    if (!World)
    {
        return;
    }
    UGameInstance* GI = World->GetGameInstance();
    if (!GI)
    {
        return;
    }
    UBlackjackNetClient* NetClient = GI->GetSubsystem<UBlackjackNetClient>();
    if (!NetClient)
    {
        return;
    }
    NetClient->SendGesture(SeatIndex, Gesture);
}
