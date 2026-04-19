#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "BlackjackDealerCharacter.generated.h"

class UAnimMontage;

/**
 * Placeholder dealer character. Designers override the skeletal mesh + animation assets
 * in a Blueprint child to use their own dealer model & montages. The C++ exposes the
 * montage slots and helper functions that BlackjackGameComponent's Blueprint bindings
 * can call from OnCardDealt / OnRoundOver / OnBigWin.
 */
UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackDealerCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    ABlackjackDealerCharacter();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Animation") UAnimMontage* DealCardMontage = nullptr;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Animation") UAnimMontage* FlipHoleMontage = nullptr;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Animation") UAnimMontage* PayPlayerMontage = nullptr;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Animation") UAnimMontage* CollectChipsMontage = nullptr;

    UFUNCTION(BlueprintCallable, Category = "Blackjack") void PlayDeal();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void PlayFlipHole();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void PlayPay();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void PlayCollect();

private:
    void PlayIfValid(UAnimMontage* M);
};
