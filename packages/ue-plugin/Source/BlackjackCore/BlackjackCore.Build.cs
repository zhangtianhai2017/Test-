using UnrealBuildTool;

public class BlackjackCore : ModuleRules
{
    public BlackjackCore(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        bUseUnity = false;

        PublicDependencyModuleNames.AddRange(new string[] { "Core" });
        PrivateDependencyModuleNames.AddRange(new string[] {
            "CoreUObject", "Engine", "Json", "JsonUtilities"
        });
    }
}
