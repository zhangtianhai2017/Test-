#include "BlackjackDealerCharacter.h"
#include "Animation/AnimMontage.h"
#include "Components/SkeletalMeshComponent.h"

ABlackjackDealerCharacter::ABlackjackDealerCharacter()
{
    PrimaryActorTick.bCanEverTick = false;
}

void ABlackjackDealerCharacter::PlayIfValid(UAnimMontage* M)
{
    if (!M) return;
    if (USkeletalMeshComponent* Mesh = GetMesh())
    {
        if (UAnimInstance* Anim = Mesh->GetAnimInstance()) Anim->Montage_Play(M);
    }
}

void ABlackjackDealerCharacter::PlayDeal()    { PlayIfValid(DealCardMontage); }
void ABlackjackDealerCharacter::PlayFlipHole(){ PlayIfValid(FlipHoleMontage); }
void ABlackjackDealerCharacter::PlayPay()     { PlayIfValid(PayPlayerMontage); }
void ABlackjackDealerCharacter::PlayCollect() { PlayIfValid(CollectChipsMontage); }
