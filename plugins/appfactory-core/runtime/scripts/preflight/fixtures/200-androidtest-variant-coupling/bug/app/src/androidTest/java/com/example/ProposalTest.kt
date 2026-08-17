package com.example

import com.example.debug.fakeProposal
import org.junit.Test

class ProposalTest {
    @Test fun renders() {
        val p = fakeProposal()
        assert(p.action.isNotEmpty())
    }
}
