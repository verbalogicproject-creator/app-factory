dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.totally.absent.artifact)

    // REGRESSION GUARD: a comment naming an alias is documentation, not a usage.
    //
    // Before check 010 stripped comments, this line failed the check on correct code.
    // It was hit for real while removing the Kotlin plugin for AGP 9, where the commit
    // deliberately left a note saying why the alias is gone.
    //
    // This is the mirror of check 060's bug-comment-only fixture: there a comment must
    // not count as PRESENCE, here it must not count as USE.
    // NO alias(libs.plugins.kotlin.android) -- AGP 9 provides Kotlin support itself
}
