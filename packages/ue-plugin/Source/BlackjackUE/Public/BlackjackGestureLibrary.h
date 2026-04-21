#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlackjackNetClient.h"  // for EBlackjackGesture
#include "BlackjackGestureLibrary.generated.h"

/**
 * Static helpers for mapping user input (keybinds) to gesture send calls
 * and displaying readable names in UI.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackGestureLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Short display string for UI chips, e.g. "自信" / "Confident". Pass the
     *  language code ("zh" or "en") to pick the locale. */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Gesture")
    static FText GestureDisplayName(EBlackjackGesture Gesture, const FString& Language);

    /** Returns a single-letter hint (for keybind labels): C / N / P / T / S / * */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Gesture")
    static FString GestureShortLabel(EBlackjackGesture Gesture);

    /** Returns every enum value in UI-order. Useful for populating a radial
     *  menu or button grid. */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Gesture")
    static TArray<EBlackjackGesture> AllGestures();

    /** Convenience: resolve a short key press (e.g. "c", "n", "p", "t", "s", "celebrate")
     *  to a gesture. Returns false when no match. */
    UFUNCTION(BlueprintCallable, Category="Blackjack|Gesture")
    static bool GestureFromKey(const FString& Key, EBlackjackGesture& OutGesture);

    /** Wire hint: call on the UBlackjackNetClient to send. This is just a
     *  re-exported BlueprintCallable forward that graphs can drag; included
     *  so designers don't need to cast the subsystem explicitly. */
    UFUNCTION(BlueprintCallable, Category="Blackjack|Gesture", meta=(WorldContext="WorldContextObject"))
    static void SendGesture(UObject* WorldContextObject, int32 SeatIndex, EBlackjackGesture Gesture);
};
